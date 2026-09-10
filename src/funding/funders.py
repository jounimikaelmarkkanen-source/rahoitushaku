"""Funder-owned calls and schemes. Deterministic extraction with source evidence."""
import re
from datetime import UTC, date, datetime
from html import unescape
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

import httpx
from bs4 import BeautifulSoup

from funding.adapters import Batch
from funding.domain import Due, Record, canonical_url, clean_html

FI_DATE = re.compile(r"(?<!\d)(\d{1,2})\.(\d{1,2})\.(\d{4})(?!\d)(?:\s+(?:klo\s*)?(\d{1,2})[:.](\d{2}))?")
FI_SHORT_RANGE = re.compile(r"(?<!\d)(\d{1,2})\.(\d{1,2})\.\s*[–-]\s*(\d{1,2})\.(\d{1,2})\.(\d{4})(?!\d)")
STATES = {"avoinna": "open", "avoin": "open", "haettavana": "open", "tulossa": "forthcoming",
          "päättynyt": "closed", "suljettu": "closed", "jatkuva": "rolling",
          "open": "open", "closed": "closed", "open call": "open", "closed call": "closed",
          "forthcoming": "forthcoming", "käynnissä": "open"}
MONTHS = {month.casefold(): index for index, month in enumerate(
    ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"), 1)}
EN_DATE = re.compile(r"(?<!\d)(\d{1,2})\s+("+"|".join(MONTHS)+r")\s+(\d{4})(?!\d)(?:[,\s(]+(\d{1,2})[:.](\d{2}))?", re.I)
ISO_DATE = re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?:[ T]+(\d{2}):(\d{2})(?::\d{2})?)?(?!\d)")


def semantic_text(node):
    """Include published accordion templates; exclude executable and navigation content."""
    copy = BeautifulSoup(str(node), "html.parser")
    for item in copy.select("script,style,noscript,nav,footer,form,.people-list"):
        item.decompose()
    for item in copy.select("template"):
        item.unwrap()
    # BeautifulSoup retains TemplateString subclasses after unwrap; reparsing
    # makes accordion text visible to get_text(), including eligibility clauses.
    copy = BeautifulSoup(str(copy), "html.parser")
    return re.sub(r"[ \t]+", " ", copy.get_text("\n", strip=True)).strip()


def dates_in_label(label, timezone):
    """Only call this on an identified date field, never on arbitrary page text."""
    result = []
    for match in FI_DATE.finditer(label):
        day, month, year, hour, minute = match.groups()
        d = date(int(year), int(month), int(day))
        stamp = datetime(d.year, d.month, d.day, int(hour), int(minute), tzinfo=ZoneInfo(timezone)) if hour else None
        result.append(Due(due_on=d, due_at=stamp.astimezone(UTC).replace(tzinfo=None) if stamp else None,
                          original=match.group(0), timezone=timezone))
    short_range = FI_SHORT_RANGE.search(label)
    if short_range:
        start_day, start_month, end_day, end_month, year = map(int, short_range.groups())
        start, end = date(year, start_month, start_day), date(year, end_month, end_day)
        if start <= end and len(result) == 1:
            result.insert(0, Due(due_on=start, original=short_range.group(0), timezone=timezone))
    if not result:
        for match in ISO_DATE.finditer(label):
            year, month, day, hour, minute = match.groups()
            d = date(int(year), int(month), int(day))
            # Literal CET/CEST is retained, including a publisher's possible
            # mismatch with local daylight saving. Do not silently correct it.
            zone = "Etc/GMT-2" if re.search(r"\bCEST\b", label) else "Etc/GMT-1" if re.search(r"\bCET\b", label) else timezone
            stamp = datetime(d.year, d.month, d.day, int(hour), int(minute), tzinfo=ZoneInfo(zone)) if hour else None
            result.append(Due(due_on=d, due_at=stamp.astimezone(UTC).replace(tzinfo=None) if stamp else None,
                              original=label.strip(), timezone=zone))
    if not result:
        for match in EN_DATE.finditer(label):
            day, month, year, hour, minute = match.groups()
            d = date(int(year), MONTHS[month.casefold()], int(day))
            zone = "Etc/GMT-2" if re.search(r"\bCEST\b", label) else "Etc/GMT-1" if re.search(r"\bCET\b", label) else timezone
            stamp = datetime(d.year, d.month, d.day, int(hour), int(minute), tzinfo=ZoneInfo(zone)) if hour else None
            result.append(Due(due_on=d, due_at=stamp.astimezone(UTC).replace(tzinfo=None) if stamp else None,
                              original=label.strip(), timezone=zone))
    return result


def eligibility_excerpt(text):
    # An excerpt is evidence for review, never an eligibility decision for Tampere.
    lines = [line for line in text.splitlines() if re.search(
        r"voivat hakea|voi hakea|hakukelpoi|hakijaksi|who can apply|eligible applicant|eligibility|public sector|julkiset|julkisen sektorin|yhteisöt|organisations can apply",
        line, re.I)]
    return "\n".join(lines)[:18000]


def require_main(html, config):
    soup = BeautifulSoup(html, "html.parser")
    main = soup.select_one(config.get("selector", "main, article, #content"))
    if main is None or len(semantic_text(main)) < 100:
        raise ValueError("Funder main content missing or unexpectedly short")
    return soup, main


def sitra_record(row):
    if row["type"] != "funding_request" or row["status"] != "publish":
        raise ValueError("Not a published Sitra funding request")
    soup = BeautifulSoup(row["content"]["rendered"], "html.parser")
    metadata = {}
    for key in ("program", "start-datetime", "end-datetime", "status"):
        node = soup.select_one(f".single-meta--{key} .single-meta__data")
        metadata[key] = node.get_text(" ", strip=True) if node else ""
    if not any(metadata.values()):
        raise ValueError("Sitra funding metadata missing; parser review required")
    starts = dates_in_label(metadata["start-datetime"], "Europe/Helsinki")
    ends = dates_in_label(metadata["end-datetime"], "Europe/Helsinki")
    description = semantic_text(soup)
    record = Record(external_id=str(row["id"]), canonical_url=row["link"],
                    title=clean_html(row["title"]["rendered"]), description=description,
                    funder="Sitra", programme=metadata["program"], record_kind="call",
                    source_status=STATES.get(metadata["status"].casefold(), "unknown"),
                    opens_on=starts[0].due_on if starts else None, deadlines=ends,
                    deadline_model="single-stage" if ends else "unknown", geographic_scope="finland",
                    detail_level="full", eligibility_text=eligibility_excerpt(description),
                    quality_flags=["eligibility_excerpt_requires_review"])
    raw = {"url": row["link"], "wordpress_id": row["id"], "modified_gmt": row.get("modified_gmt"),
           "title": record.title, "text": description, "metadata": metadata}
    return record, raw


def sitra(client, config):
    expected, seen, ids = None, 0, set()
    for page in range(1, config.get("max_pages", 100)+1):
        response = client.request("GET", config["api_url"], params={"per_page": 50, "page": page, "lang": "fi"})
        rows = response.json()
        total, pages = int(response.headers["X-WP-Total"]), int(response.headers["X-WP-TotalPages"])
        if not isinstance(rows, list) or (not rows and total):
            raise ValueError("Sitra returned an invalid or premature empty page")
        expected = total if expected is None else expected
        batch = Batch(expected=expected)
        if total != expected:
            batch.warnings.append("Sitra total changed during pagination; repeat run required")
        for row in rows:
            try:
                if row["id"] in ids:
                    raise ValueError("Sitra duplicate ID across pages")
                ids.add(row["id"])
                batch.items.append(sitra_record(row))
            except (KeyError, ValueError, TypeError) as exc:
                batch.rejected.append((str(exc), row))
        seen += len(rows)
        yield batch
        if page >= pages:
            if seen != expected:
                raise ValueError(f"Sitra pagination mismatch: {seen}/{expected}")
            return
    raise ValueError("Sitra pagination safety limit reached")


def html_record(title, url, description, config, *, date_label="", status_label="", detail_level="listing"):
    kind = config.get("record_kind", "call")
    # A general scheme may describe many historical/annual rounds. Never infer its
    # current status or deadline from dates elsewhere in the body.
    dates = dates_in_label(date_label, config.get("timezone", "Europe/Helsinki")) if kind == "call" else []
    opens = dates[0].due_on if len(dates) == 2 and config.get("date_is_period") else None
    ends = dates[-1:] if dates else []
    flags = ["eligibility_excerpt_requires_review", *config.get("quality_flags", [])]
    if kind == "funding_scheme":
        flags.append("scheme_not_a_dated_call")
    if kind == "advance_information":
        flags.append("advance_information_not_a_call")
    status = STATES.get(status_label.strip().casefold(), "unknown")
    if opens and ends and not status_label:
        status = "open"  # The SQL view evaluates the published interval against today.
    if dates and not status_label:
        # Only a published future deadline does not prove the round has opened.
        flags.append("opening_status_not_published_in_listing")
    eligibility = eligibility_excerpt(description)
    if config.get("eligibility_note"):
        eligibility += "\n[Lähderekisterin huomio; ei kelpoisuuspäätös] " + config["eligibility_note"]
    return Record(external_id=canonical_url(url), canonical_url=url, title=title,
                  description=description, funder=config.get("funder", config["name"]),
                  programme=config.get("programme", ""), record_kind=kind,
                  instrument=config.get("instrument", "grant"), language=config.get("language", "fi"),
                  geographic_scope=config.get("geographic_scope", "unknown"),
                  source_status=status, opens_on=opens, deadlines=ends,
                  deadline_model=config.get("deadline_model", "single-stage" if ends else "unknown"), detail_level=detail_level,
                  eligibility_text=eligibility, quality_flags=flags)


def catalogue(client, config):
    url, page_urls, record_urls = config["url"], set(), {}
    for _ in range(config.get("max_pages", 100)):
        if url in page_urls:
            raise ValueError("Funder pagination repeats a page")
        page_urls.add(url)
        response = client.request("GET", url)
        soup, main = require_main(response.text, config)
        cards = main.select(config["card_selector"])
        if not cards:
            raise ValueError("Funder cards missing; parser review required")
        batch, local_urls = Batch(), set()
        for card in cards:
            link = card if config.get("link_is_card") else card.select_one(config["link_selector"])
            if link is None or not link.get("href"):
                if config.get("skip_cards_without_link"):
                    continue
                raise ValueError("Funder card link missing")
            target = canonical_url(urljoin(str(response.url), link["href"]))
            title_node = card.select_one(config["title_selector"]) if config.get("title_selector") else link
            if title_node is None:
                raise ValueError("Funder card title missing")
            title = title_node.get_text(" ", strip=True)
            if not title or target in local_urls:
                continue
            local_urls.add(target)
            if config.get("include_url") and not re.search(config["include_url"], target):
                continue
            if config.get("exclude_title") and re.search(config["exclude_title"], title, re.I):
                continue
            if config.get("include_title") and not re.search(config["include_title"], title, re.I):
                continue
            listing_text = semantic_text(card)
            if target in record_urls:
                if record_urls[target] != listing_text:
                    raise ValueError(f"Conflicting repeated funder card: {target}")
                # Some public directories repeat identical pinned/listing cards.
                continue
            record_urls[target] = listing_text
            try:
                text = listing_text
                date_node = card.select_one(config["date_selector"]) if config.get("date_selector") else None
                state_node = card.select_one(config["status_selector"]) if config.get("status_selector") else None
                date_label = date_node.get_text(" ", strip=True) if date_node else ""
                status_label = state_node.get_text(" ", strip=True) if state_node else ""
                raw = {"listing_url": str(response.url), "url": target, "title": title, "listing_text": text,
                       "date_label": date_label, "status_label": status_label}
                level = "listing"
                if config.get("fetch_details"):
                    try:
                        detail = client.request("GET", target)
                        _, body = require_main(detail.text, config)
                        text, level = semantic_text(body), "full"
                        raw.update(text=text, resolved_url=str(detail.url))
                    except (httpx.HTTPError, ValueError, OSError, RuntimeError) as exc:
                        raw["detail_error"] = str(exc)[:1200]
                        batch.warnings.append("One or more detail pages failed; listing retained and full content needs review")
                item_config = {**config, **config.get("overrides", {}).get(target, {})}
                record = html_record(title, target, text, item_config, date_label=date_label,
                                     status_label=status_label, detail_level=level)
                if "detail_error" in raw:
                    record.quality_flags.append("detail_fetch_failed_listing_retained")
                if config.get("open_date_selector") and record.record_kind == "call":
                    start_node = card.select_one(config["open_date_selector"])
                    start_label = start_node.get_text(" ", strip=True) if start_node else ""
                    raw["open_date_label"] = start_label
                    starts = dates_in_label(start_label, config.get("timezone", "Europe/Helsinki"))
                    if starts:
                        record.opens_on = starts[0].due_on
                        if record.deadlines and not status_label:
                            # Both published interval bounds exist; the SQL view
                            # applies today's forthcoming/closed transition.
                            record.source_status = "open"
                if config.get("unpaginated_warning_selector"):
                    for node in soup.select(config["unpaginated_warning_selector"]):
                        if int(node.get("data-pages", "1")) > 1 and not config.get("next_selector"):
                            batch.warnings.append("Source advertises additional dynamic pages; only server-rendered cards collected")
                batch.items.append((record, raw))
            except (KeyError, ValueError, TypeError) as exc:
                batch.rejected.append((str(exc), {"url": target, "title": title}))
        yield batch
        next_link = soup.select_one(config["next_selector"]) if config.get("next_selector") else None
        if next_link is None:
            return
        url = urljoin(str(response.url), next_link["href"])
    raise ValueError("Funder pagination safety limit reached")


def funding_pages(client, config):
    pages = config["pages"]
    if not pages:
        raise ValueError("No configured funding scheme pages")
    seen = set()
    for entry in pages:
        url = canonical_url(entry["url"])
        if url in seen:
            raise ValueError("Duplicate configured scheme URL")
        seen.add(url)
        response = client.request("GET", url)
        _, main = require_main(response.text, {**config, **entry})
        title_node = main.select_one("h1")
        if not title_node and not entry.get("title"):
            raise ValueError("Funding scheme title missing")
        text = semantic_text(main)
        title = entry.get("title") or title_node.get_text(" ", strip=True)
        item_config = {"record_kind": "funding_scheme", **config, **entry}
        # Date selectors are evaluated on the live page, never hard-coded dates.
        date_node = main.select_one(entry["date_selector"]) if entry.get("date_selector") else None
        state_node = main.select_one(entry["status_selector"]) if entry.get("status_selector") else None
        record = html_record(title, url, text, item_config, detail_level="full",
                             date_label=date_node.get_text(" ", strip=True) if date_node else "",
                             status_label=state_node.get_text(" ", strip=True) if state_node else "")
        if entry.get("open_date_selector") and record.record_kind == "call":
            start_node = main.select_one(entry["open_date_selector"])
            starts = dates_in_label(start_node.get_text(" ", strip=True), item_config.get("timezone", "Europe/Helsinki")) if start_node else []
            if starts:
                record.opens_on = starts[0].due_on
        if entry.get("rolling_selector") and record.record_kind == "call":
            rolling = main.select_one(entry["rolling_selector"])
            if rolling and re.match(r"jatkuva haku\b", rolling.get_text(" ", strip=True), re.I):
                record.source_status, record.deadline_model, record.deadlines = "rolling", "rolling", []
        yield Batch(items=[(record, {"url": url, "resolved_url": str(response.url), "title": title, "text": text})], expected=len(pages))


def wordpress_calls(client, config):
    """Public WordPress call post type, including its closed historical records."""
    taxonomy = client.request("GET", config["status_api"], params={"per_page": 100}).json()
    statuses = {row["id"]: STATES.get(clean_html(row["name"]).casefold(), "unknown") for row in taxonomy}
    seen, expected, ids = 0, None, set()
    for page in range(1, config.get("max_pages", 100)+1):
        response = client.request("GET", config["api_url"], params={"per_page": 50, "page": page})
        rows = response.json()
        total, pages = int(response.headers["X-WP-Total"]), int(response.headers["X-WP-TotalPages"])
        if not isinstance(rows, list) or (not rows and total):
            raise ValueError("Invalid or prematurely empty WordPress call page")
        expected = total if expected is None else expected
        batch = Batch(expected=expected)
        if total != expected:
            batch.warnings.append("WordPress total changed during pagination; repeat run required")
        for row in rows:
            try:
                if row["id"] in ids or row["type"] != config["post_type"] or row["status"] != "publish":
                    raise ValueError("Duplicate or unsupported WordPress record")
                ids.add(row["id"])
                body = BeautifulSoup(row["content"]["rendered"], "html.parser")
                label_pattern = re.compile(r"^(?:call closes|deadline for (?:applications|proposals)|application deadline|submission deadline)\s*:", re.I)
                labels = [p.get_text(" ", strip=True) for p in body.select("p,li,tr")
                          if label_pattern.search(p.get_text(" ", strip=True))]
                state_values = {statuses.get(code, "unknown") for code in row.get(config["status_taxonomy"], [])}
                if len(state_values) > 1:
                    raise ValueError("Conflicting WordPress call statuses")
                status = next(iter(state_values), "unknown")
                record = html_record(unescape(clean_html(row["title"]["rendered"])), row["link"], semantic_text(body), config,
                                     date_label="\n".join(labels), status_label=status, detail_level="full")
                record.external_id = str(row["id"])
                batch.items.append((record, row))
            except (KeyError, ValueError, TypeError) as exc:
                batch.rejected.append((str(exc), row))
        seen += len(rows)
        yield batch
        if page >= pages:
            if seen != expected:
                raise ValueError(f"WordPress pagination mismatch: {seen}/{expected}")
            return
    raise ValueError("WordPress pagination safety limit reached")


FUNDERS = {"sitra": sitra, "funder_catalogue": catalogue, "funding_pages": funding_pages,
           "wordpress_calls": wordpress_calls}
