"""Bounded, polite public HTTP access. No credentials or arbitrary API-provided URLs."""
import ipaddress
import socket
import threading
import time
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx

from funding.settings import Settings


class RateLimited(RuntimeError):
    """A shared origin pause, persisted by the document collector across restarts."""
    def __init__(self, origin, retry_at, attempted=False):
        self.origin, self.retry_at, self.attempted = origin, retry_at, attempted
        super().__init__(f"RATE_LIMIT|{origin}|{retry_at.isoformat()}")


class PublicClient:
    cooldown_lock = threading.Lock()
    cooldowns = {}

    @classmethod
    def defer_origin(cls, origin, retry_at):
        with cls.cooldown_lock:
            cls.cooldowns[origin] = max(retry_at, cls.cooldowns.get(origin, retry_at))

    @classmethod
    def check_cooldown(cls, url):
        p = urlsplit(url)
        origin = f"{p.scheme}://{p.netloc}"
        with cls.cooldown_lock:
            until = cls.cooldowns.get(origin)
        if until and until > datetime.now(UTC).replace(tzinfo=None):
            raise RateLimited(origin, until)

    def __init__(self, cfg: Settings, allowed_hosts: list[str], transport=None):
        self.cfg = cfg
        self.allowed_hosts = set(allowed_hosts)
        self.client = httpx.Client(
            timeout=cfg.request_timeout, headers={"User-Agent": cfg.user_agent},
            follow_redirects=False, transport=transport,
        )
        self.robots: dict[str, RobotFileParser | None] = {}
        self.last_request = 0.0
        self.transport = transport

    def validate(self, url):
        p = urlsplit(url)
        if p.scheme != "https" or p.hostname not in self.allowed_hosts or p.username or p.password:
            raise ValueError("URL is outside the source's approved public HTTPS hosts")
        if p.port not in (None, 443):
            raise ValueError("Nonstandard port is not allowed")
        if self.transport is None:
            for info in socket.getaddrinfo(p.hostname, 443, type=socket.SOCK_STREAM):
                if not ipaddress.ip_address(info[4][0]).is_global:
                    raise ValueError("Non-public address is not allowed")

    def _request(self, method, url, **kwargs):
        self.validate(url)
        for attempt in range(3):
            self.check_cooldown(url)
            time.sleep(max(0, self.cfg.min_request_interval - (time.monotonic() - self.last_request)))
            self.last_request = time.monotonic()
            try:
                with self.client.stream(method, url, **kwargs) as response:
                    body = bytearray()
                    for chunk in response.iter_bytes():
                        body.extend(chunk)
                        if len(body) > self.cfg.max_response_bytes:
                            raise ValueError("Response exceeds configured maximum size")
                    headers = {k: v for k, v in response.headers.items() if k.lower() not in ("content-encoding", "content-length")}
                    r = httpx.Response(response.status_code, headers=headers, content=bytes(body), request=response.request)
                if r.status_code == 429:
                    stamp = datetime.now(UTC).replace(tzinfo=None)
                    retry = r.headers.get("Retry-After", "")
                    try:
                        until = stamp + timedelta(seconds=max(1, int(retry)))
                    except (ValueError, OverflowError):
                        try:
                            until = parsedate_to_datetime(retry)
                            if until.tzinfo is None:
                                until = until.replace(tzinfo=UTC)
                            until = until.astimezone(UTC).replace(tzinfo=None)
                            until = max(until, stamp+timedelta(seconds=1))
                        except (TypeError, ValueError, OverflowError):
                            until = stamp+timedelta(minutes=5)
                    p = urlsplit(url)
                    origin = f"{p.scheme}://{p.netloc}"
                    self.defer_origin(origin, until)
                    raise RateLimited(origin, until, attempted=True)
                if r.status_code not in (500, 502, 503, 504):
                    return r
                if attempt == 2:
                    r.raise_for_status()
                retry_after = r.headers.get("Retry-After", "")
                delay = min(30, int(retry_after)) if retry_after.isdigit() else 2 ** (attempt + 1)
                time.sleep(delay)
            except (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError):
                if attempt == 2:
                    raise
                time.sleep(2 ** (attempt + 1))
        raise RuntimeError("HTTP retries exhausted")

    def _robots_allowed(self, url):
        p = urlsplit(url)
        origin = f"{p.scheme}://{p.netloc}"
        if origin not in self.robots:
            robots_url = origin + "/robots.txt"
            for _ in range(5):
                r = self._request("GET", robots_url)
                if not r.is_redirect:
                    break
                robots_url = str(r.url.join(r.headers["location"]))
                self.validate(robots_url)
            else:
                raise ValueError("Too many robots.txt redirects")
            if r.status_code == 404:
                self.robots[origin] = None
            else:
                r.raise_for_status()
                robot = RobotFileParser()
                robot.parse(r.text.splitlines())
                self.robots[origin] = robot
        robot = self.robots[origin]
        if robot and not robot.can_fetch(self.cfg.user_agent, url):
            raise PermissionError("robots.txt disallows collection for this path")
        if robot:
            delay = robot.crawl_delay(self.cfg.user_agent) or robot.crawl_delay("*") or 0
            if delay > 60:
                raise ValueError("Source crawl-delay exceeds supported job pacing")
            time.sleep(max(0, delay - (time.monotonic() - self.last_request)))

    def request(self, method, url, **kwargs):
        for _ in range(5):
            self.validate(url)
            self.check_cooldown(url)
            self._robots_allowed(url)
            r = self._request(method, url, **kwargs)
            if r.status_code == 304 and method == "GET":
                return r
            if r.is_redirect:
                if method != "GET":
                    raise ValueError("POST redirect requires source review")
                url = str(r.url.join(r.headers["location"]))
                continue
            r.raise_for_status()
            return r
        raise ValueError("Too many redirects")

    def close(self):
        self.client.close()
