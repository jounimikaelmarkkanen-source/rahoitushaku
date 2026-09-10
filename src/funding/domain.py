import hashlib
import json
import re
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import NAMESPACE_URL, uuid5
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from bs4 import BeautifulSoup
from pydantic import BaseModel, Field, field_validator


def now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def dump(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def clean_html(value: str | None) -> str:
    if "<" not in (value or ""):
        return (value or "").strip()
    soup = BeautifulSoup(value or "", "html.parser")
    for el in soup.select("script,style,noscript"):
        el.decompose()
    return re.sub(r"[ \t]+", " ", soup.get_text("\n", strip=True)).strip()


def translated(value) -> str:
    if isinstance(value, str):
        return clean_html(value)
    if isinstance(value, dict):
        return clean_html(value.get("fi") or value.get("en") or value.get("sv") or "")
    return ""


def canonical_url(url: str) -> str:
    p = urlsplit(url)
    if p.scheme not in ("https", "http") or not p.hostname or p.username or p.password:
        raise ValueError("A public HTTP(S) source URL is required")
    query = urlencode(sorted((k, v) for k, v in parse_qsl(p.query) if not k.lower().startswith("utm_")))
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path.rstrip("/") or "/", query, ""))


def opportunity_id(url: str) -> str:
    return str(uuid5(NAMESPACE_URL, canonical_url(url)))


def parse_time(value: str | None) -> datetime | None:
    if not value or len(value) <= 10:
        return None
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if not dt.tzinfo:
        raise ValueError(f"Timezone missing from timestamp: {value}")
    return dt.astimezone(UTC).replace(tzinfo=None)


class Due(BaseModel):
    due_on: date
    due_at: datetime | None = None
    original: str
    timezone: str = "Europe/Helsinki"


def due(value: str, timezone: str = "UTC") -> Due:
    dt = parse_time(value)
    # Calendar date is retained as published; no invented time for date-only values.
    return Due(due_on=date.fromisoformat(value[:10]), due_at=dt, original=value, timezone=timezone)


class Label(BaseModel):
    kind: Literal["theme", "region", "applicant", "keyword"]
    value: str = Field(max_length=200)
    basis: Literal["source", "rule"] = "source"


class Record(BaseModel):
    external_id: str = Field(min_length=1, max_length=400)
    canonical_url: str = Field(max_length=2048)
    title: str = Field(min_length=1, max_length=1000)
    description: str = ""
    funder: str = Field(default="", max_length=500)
    programme: str = Field(default="", max_length=200)
    record_kind: Literal["call", "funding_scheme", "advance_information"] = "call"
    instrument: Literal["grant", "loan", "guarantee", "prize", "technical_assistance", "other"] = "grant"
    language: str = "fi"
    source_status: Literal["open", "forthcoming", "closed", "rolling", "unknown", "cancelled"] = "unknown"
    opens_on: date | None = None
    deadline_on: date | None = None
    deadline_at: datetime | None = None
    deadline_expires_at: datetime | None = None
    deadline_model: str = "unknown"
    total_budget: Decimal | None = Field(default=None, ge=0)
    grant_max: Decimal | None = Field(default=None, ge=0)
    funding_rate: Decimal | None = Field(default=None, ge=0, le=100)
    currency: str | None = None
    eligibility_text: str = ""
    geographic_scope: Literal["eu", "finland", "pirkanmaa", "other_region", "unknown", "international"] = "unknown"
    detail_level: Literal["listing", "full", "manual"] = "listing"
    quality_flags: list[str] = Field(default_factory=list)
    deadlines: list[Due] = Field(default_factory=list)
    tags: list[Label] = Field(default_factory=list)

    @field_validator("canonical_url")
    @classmethod
    def normalise_url(cls, value):
        return canonical_url(value)


THEMES = {
    "Ilmasto ja energia": ["climat", "ilmasto", "energia", "energy", "hiilineutra", "decarbon"],
    "Digitalisaatio ja tekoäly": ["digital", "tekoäly", "artificial intelligence", "data space", "cyber"],
    "Osaaminen ja koulutus": ["education", "koulutus", "osaami", "skills", "learning"],
    "Työllisyys ja elinvoima": ["employment", "työllis", "elinvoima", "entrepreneur", "innovation", "innovaat"],
    "Kulttuuri ja liikunta": ["culture", "kulttuuri", "liikunta", "sport", "heritage"],
    "Hyvinvointi ja osallisuus": ["wellbeing", "hyvinvoin", "health", "inclusion", "osallisu", "yhdenvertais"],
    "Liikenne ja kaupunkiympäristö": ["mobility", "transport", "liikenne", "urban", "kaupunki", "built environment"],
    "Luonto ja kiertotalous": ["biodivers", "luonto", "circular", "kiertotal", "water", "vesistö"],
    "Turvallisuus ja varautuminen": ["security", "turvallis", "resilience", "varautu", "disaster"],
}


def enrich(record: Record) -> Record:
    text = (record.title + " " + record.description).casefold()
    for theme, words in THEMES.items():
        if any(word in text for word in words):
            record.tags.append(Label(kind="theme", value=theme, basis="rule"))
    record.tags = list({(t.kind, t.value): t for t in record.tags}.values())
    if record.deadlines:
        last = max(record.deadlines, key=lambda d: (d.due_on, d.due_at or datetime.min))
        record.deadline_on, record.deadline_at = last.due_on, last.due_at
        if last.due_at:
            record.deadline_expires_at = last.due_at
        else:
            try:
                zone = ZoneInfo(last.timezone)
            except ZoneInfoNotFoundError:
                zone = ZoneInfo("UTC")
                record.quality_flags.append("deadline_timezone_needs_review")
            record.deadline_expires_at = datetime.combine(last.due_on + timedelta(days=1), time.min, zone).astimezone(UTC).replace(tzinfo=None)
    if not record.eligibility_text:
        record.quality_flags.append("eligibility_not_extracted")
    if record.deadline_on is None:
        record.quality_flags.append("deadline_unknown")
    if record.deadline_model in ("two-stage", "multiple-cut-off"):
        record.quality_flags.append("stage_access_must_be_checked")
    record.quality_flags = sorted(set(record.quality_flags))
    return record
