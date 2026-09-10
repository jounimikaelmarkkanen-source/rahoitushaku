"""Small independent adapters. Parser drift fails visibly, never as an empty success."""
import json
import re
import sqlite3
from contextlib import closing
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from tempfile import TemporaryDirectory
from urllib.parse import quote, unquote
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from funding.domain import Label, Record, clean_html, due, now, parse_time, translated


@dataclass
class Batch:
    items: list[tuple[Record, dict]] = field(default_factory=list)
    rejected: list[tuple[str, dict]] = field(default_factory=list)
    expected: int | None = None
    warnings: list[str] = field(default_factory=list)


def fi_date(value):
    dt = parse_time(value)
    if dt:
        from datetime import UTC
        return dt.replace(tzinfo=UTC).astimezone(ZoneInfo("Europe/Helsinki")).date()
    return date.fromisoformat(value[:10]) if value else None


def hae_record(row):
    ext = row["hakuasianAsianumero"]
    end = row.get("hakuPaattyyDateTimeUtc")
    start = row.get("hakuAlkaaDateTimeUtc")
    end_at = parse_time(end)
    opens = fi_date(start)
    status = "rolling" if row.get("hakuTyyppi") == "Jatkuva" else "open"
    if end_at and end_at < now():
        status = "closed"
    elif opens and opens > now().date():
        status = "forthcoming"
    elif not start:
        status = "unknown"
    dates = [due(end, "Europe/Helsinki")] if end else []
    if dates:
        dates[0].due_on = fi_date(end)
    return Record(
        external_id=ext, canonical_url=f"https://www.haeavustuksia.fi/fi/haku/{quote(ext, safe='')}",
        title=translated(row["nimi"]), description=translated(row.get("kuvaus")),
        funder=translated(row.get("vastuullinenJarjestajaOrganisaatio", {}).get("nimi")),
        programme="Valtionavustukset", opens_on=opens, source_status=status,
        deadline_model="rolling" if row.get("hakuTyyppi") == "Jatkuva" else "single-stage",
        deadlines=dates, geographic_scope="unknown",
        quality_flags=["geographic_eligibility_not_extracted"],
    )


def hae(client, config):
    page, seen, expected, ids = 1, 0, None, set()
    while page <= config.get("max_pages", 200):
        response = client.request("GET", config["url"], params={
            "Pagination.Page": page, "Pagination.PageSize": 100, "Language": "fi",
            "ShowFuture": "true", "ShowOngoing": "true", "ShowEnded": "true", "HideExternal": "false",
        }).json()
        rows = response["hakuilmoitukset"]
        total = int(response["totalCount"])
        expected = total if expected is None else expected
        batch = Batch(expected=expected)
        if total != expected:
            batch.warnings.append("Source total changed during pagination; repeat run required")
        for row in rows:
            try:
                key = row["hakuasianAsianumero"]
                if key in ids:
                    raise ValueError("Duplicate identifier across pages")
                ids.add(key)
                batch.items.append((hae_record(row), row))
            except (KeyError, ValueError, TypeError) as exc:
                batch.rejected.append((str(exc), row))
        seen += len(rows)
        yield batch
        if page >= int(response["pageCount"]):
            if seen != expected:
                raise ValueError(f"Pagination count mismatch: {seen}/{expected}")
            return
        if not rows:
            raise ValueError("Empty page before advertised end")
        page += 1
    raise ValueError("Pagination safety limit reached")


def eura_data(html):
    soup = BeautifulSoup(html, "html.parser")
    for script in soup.select("script"):
        text = script.string or ""
        if text.startswith("%7B%22preRenderData%22"):
            return json.loads(unquote(text))["preRenderData"]
    raise ValueError("EURA public preRenderData not found; adapter needs review")


def eura_record(row, codes):
    areas = [codes["maakunta"].get(str(code), {}).get("fi", str(code)) for code in row.get("maakunnat", [])]
    region = "finland" if row.get("alue") == "VALTAKUNNALLINEN" else (
        "pirkanmaa" if "Pirkanmaa" in areas else "other_region" if areas else "unknown"
    )
    funder = codes["viranomainen"].get(str(row.get("viranomainen")), {}).get("fi", str(row.get("viranomainen", "")))
    dates = row.get("hakuaika", {})
    end = dates.get("loppu")
    status = {"avoin": "open", "tulossa": "forthcoming", "paattynyt": "closed"}.get(row.get("tila"), "unknown")
    if row.get("jatkuvaHaku"):
        status = "rolling"
    amount = row.get("kokonaistuki")
    try:
        amount = Decimal(str(amount).replace(" ", "").replace("\u00a0", "").replace(",", ".")) if amount else None
    except InvalidOperation:
        amount = None
    return Record(
        external_id=row["id"], canonical_url=f"https://eura2021.fi/hakuilmoitukset/hakuilmoitus/{row['id']}",
        title=row["otsikko"], description=clean_html(row.get("kuvaus", "")), funder=funder,
        programme=row.get("rahasto", "EURA 2021"), source_status=status,
        opens_on=date.fromisoformat(dates["alku"]) if dates.get("alku") else None,
        deadlines=[due(end, "Europe/Helsinki")] if end else [],
        deadline_model="rolling" if row.get("jatkuvaHaku") else "single-stage",
        geographic_scope=region, total_budget=amount, currency="EUR" if amount is not None else None,
        detail_level="full" if "kuvaus" in row else "listing",
        tags=[Label(kind="region", value=a) for a in areas],
        quality_flags=["date_only_deadline"] if end else [],
    )


def eura(client, config):
    data = eura_data(client.request("GET", config["url"]).text)
    rows = data["hankehaku"]
    if not isinstance(rows, list) or not rows:
        raise ValueError("EURA list is unexpectedly empty or malformed")
    batch = Batch(expected=len(rows))
    for row in rows:
        try:
            record = eura_record(row, data["koodisto"])
            batch.items.append((record, row))
        except (KeyError, TypeError, ValueError) as exc:
            batch.rejected.append((str(exc), row))
    yield batch


def first(metadata, key, default=""):
    value = metadata.get(key)
    return value[0] if isinstance(value, list) and value else value if isinstance(value, str) else default


def eu_record(row):
    meta = row["metadata"]
    identifier = first(meta, "identifier")
    kind = first(meta, "type")
    if kind not in ("1", "8"):
        raise ValueError("Not a supported funding topic type")
    if kind == "1" and (not identifier or len(identifier) > 400 or re.search(r"[\x00-\x1f]", identifier)):
        raise ValueError("Missing or unsupported funding topic identifier")
    programme = identifier.split("-")[0] if identifier else "EU cascade funding"
    title = first(meta, "title") or row.get("content", "")
    url = f"https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/opportunities/topic-details/{quote(identifier.lower(), safe='')}"
    if kind == "8":
        call_id = first(meta, "callccm2Id")
        if not call_id.isdigit():
            raise ValueError("Cascade call ID missing")
        identifier = "cascade:" + call_id
        title = first(meta, "caName") or row.get("content") or title
        url = f"https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/opportunities/competitive-calls-cs/{call_id}"
    status = {"31094501": "forthcoming", "31094502": "open", "31094503": "closed"}.get(first(meta, "status"), "unknown")
    raw_dates = meta.get("deadlineDate") or []
    start = first(meta, "startDate")
    return Record(
        external_id=identifier, canonical_url=url, title=title,
        description=clean_html(row.get("content") or row.get("summary", "")),
        funder="European Commission / EU", programme=programme, source_status=status, language="en",
        deadlines=[due(value, "UTC (source offset)") for value in sorted(set(raw_dates))],
        opens_on=date.fromisoformat(start[:10]) if start else None,
        deadline_model=first(meta, "deadlineModel", "unknown"), geographic_scope="eu",
        quality_flags=["consortium_and_country_rules_not_extracted"],
    )


def eu(client, config):
    # Public metadata is large. Stage it on ephemeral disk rather than retaining
    # the entire EU catalogue in the collector container's memory.
    with TemporaryDirectory(prefix="funding-eu-") as directory:
        with closing(sqlite3.connect(f"{directory}/topics.db")) as stage:
            stage.execute("CREATE TABLE variants (topic TEXT NOT NULL, raw_json TEXT NOT NULL)")
            stage.execute("CREATE INDEX ix_topic ON variants(topic)")
            yield from _eu(client, config, stage)


def _eu(client, config, stage):
    # Each partition stays below the corporate Search API's 10,000-result window.
    # Date ranges are half-open and the undated partition is collected separately.
    base = [
        {"terms": {"type": ["1", "8"]}},
        {"terms": {"status": ["31094501", "31094502", "31094503"]}},
        {"term": {"language": "en"}},
    ]
    document_count, expected_total = 0, 0

    def request_page(extra, page):
        query = {"bool": {"must": base + extra}}
        return client.request("POST", config["url"], params={
            "apiKey": "SEDIA", "text": "***", "pageSize": 50, "pageNumber": page,
        }, files={"query": ("query.json", json.dumps(query), "application/json")}).json()

    def partition(extra, lower, upper, depth=0):
        nonlocal document_count, expected_total
        first_page = request_page(extra, 1)
        total = int(first_page["totalResults"])
        if total >= 9000:
            if depth >= 18 or (upper-lower).days < 2:
                raise ValueError("EU partition exceeds the search window; finer partitioning needed")
            pivot = lower + (upper-lower)//2
            cutoff = pivot.isoformat()+"T00:00:00Z"
            yield from partition(extra+[{"range": {"startDate": {"lt": cutoff}}}], lower, pivot, depth+1)
            yield from partition(extra+[{"range": {"startDate": {"gte": cutoff}}}], pivot, upper, depth+1)
            return
        expected_total += total
        page, fetched = 1, 0
        while True:
            data = first_page if page == 1 else request_page(extra, page)
            batch = Batch()
            if int(data["totalResults"]) != total:
                batch.warnings.append("Source total changed during pagination; repeat run required")
            rows = data["results"]
            for row in rows:
                try:
                    record = eu_record(row)
                    # Mirrors and action types can repeat a topic. Keep every raw document;
                    # the topic/cascade-call identity, rather than a project ID, is the key.
                    stage.execute("INSERT INTO variants (topic,raw_json) VALUES (?,?)", (record.external_id, json.dumps(row, ensure_ascii=False)))
                except (KeyError, TypeError, ValueError) as exc:
                    batch.rejected.append((str(exc), row))
            fetched += len(rows)
            document_count += len(rows)
            stage.commit()
            yield batch  # lets the collector renew its lease between every HTTP page
            if fetched >= total:
                if fetched != total:
                    raise ValueError(f"Pagination count mismatch: {fetched}/{total}")
                break
            if not rows or page >= config.get("max_pages", 500):
                raise ValueError("Empty or truncated EU partition")
            page += 1

    yield from partition([{"exists": {"field": "startDate"}}], date(1900, 1, 1), date(2300, 1, 1))
    yield from partition([{"bool": {"must_not": [{"exists": {"field": "startDate"}}]}}], date(1900, 1, 1), date(2300, 1, 1))
    if document_count != expected_total:
        raise ValueError("EU partition reconciliation failed")
    out = Batch(expected=expected_total)
    for topic, in stage.execute("SELECT DISTINCT topic FROM variants ORDER BY topic"):
        documents = [json.loads(raw) for raw, in stage.execute("SELECT raw_json FROM variants WHERE topic=?", (topic,))]
        variants = [(eu_record(raw), raw) for raw in documents]
        record = preferred_eu_variant(variants)
        out.items.append((record, {"documents": [raw for _, raw in variants]}))
        if len(out.items) >= 200:
            yield out
            out = Batch(expected=expected_total)
    if out.items:
        yield out


def preferred_eu_variant(variants):
    variants.sort(key=lambda pair: (
        first(pair[1]["metadata"], "DATASOURCE") == "SEDIA",
        first(pair[1]["metadata"], "esDA_QueueDate") or first(pair[1]["metadata"], "es_SortDate"),
        str(pair[1].get("reference", "")),
    ))
    record = variants[-1][0]
    if len(variants) > 1:
        record.quality_flags.append("multiple_source_documents_for_topic")
        if len({tuple(d.original for d in rec.deadlines) for rec, _ in variants}) > 1:
            record.quality_flags.append("conflicting_source_deadlines")
    # The selected document supplies the dates. Old mirrors must not extend a deadline.
    return record


ADAPTERS = {"haeavustuksia": hae, "eura2021": eura, "eu_funding": eu}
