"""User-selected funding routes, with portable SQL predicates and explicit coverage."""
import json
from pathlib import Path

from sqlalchemy import and_, case, func, or_, select

from funding.domain import now


def load_priorities(path=Path("config/priorities.json")):
    rows = json.loads(path.read_text())
    if len({p["id"] for p in rows}) != len(rows):
        raise ValueError("Priority IDs must be unique")
    for priority in rows:
        if not priority["rules"] or any(not rule for rule in priority["rules"]):
            raise ValueError("Priority rules must not match the entire registry")
    return rows


def priority_predicate(view, priority):
    alternatives = []
    for rule in priority["rules"]:
        conditions = []
        for key, values in rule.items():
            if not values:
                raise ValueError("Priority rule must not contain an empty value list")
            if key in ("source_id", "funder", "programme", "record_kind"):
                conditions.append(view.c[key].in_(values))
            elif key in ("title_contains", "external_id_prefix"):
                column = view.c.title if key == "title_contains" else view.c.external_id
                conditions.append(or_(*(func.lower(column).contains(v.lower(), autoescape=True)
                                         if key == "title_contains" else column.startswith(v, autoescape=True)
                                         for v in values)))
            else:
                raise ValueError(f"Unsupported priority rule: {key}")
        alternatives.append(and_(*conditions))
    return or_(*alternatives)


def priority_directory(engine, view, sources, priorities):
    """No source/listing/document count is interpreted as verified completeness."""
    source_index = {s["id"]: s for s in sources}
    result = []
    # Evaluate the document-coverage view once for all groups. One query per
    # group otherwise repeats the expensive shared-document joins 12 times.
    measures = {
        "records": None,
        "calls": view.c.record_kind == "call",
        "schemes": view.c.record_kind == "funding_scheme",
        "advance_information": view.c.record_kind == "advance_information",
        "current": view.c.effective_status.in_(["open", "forthcoming", "rolling"]),
        "collected_unverified": view.c.content_state == "collected_unverified",
    }
    aggregates = []
    for index, priority in enumerate(priorities):
        matches = priority_predicate(view, priority)
        for key, condition in measures.items():
            selected = matches if condition is None else and_(matches, condition)
            aggregates.append(func.coalesce(func.sum(case((selected, 1), else_=0)), 0).label(f"p{index}_{key}"))
    if not aggregates:
        raise ValueError("No priority groups configured")
    with engine.connect() as conn:
        totals = conn.execute(select(*aggregates)).mappings().one()
        for index, priority in enumerate(priorities):
            counts = {key: totals[f"p{index}_{key}"] for key in measures}
            relevant = [source_index[s] for s in priority["sources"] if s in source_index]
            missing = [s for s in priority["sources"] if s not in source_index]
            issues = [s["id"] for s in relevant if not s["enabled"] or s["stale"] or s["health"] != "success"]
            result.append({**priority, **counts, "missing_sources": missing, "source_issues": issues,
                           "source_status": [{k: s[k] for k in ("id", "name", "collection_level", "health", "stale", "last_success_at", "last_error")} for s in relevant],
                           "complete_universe_claimed": False})
    return {"items": result, "as_of_utc": now(),
            "note": "Ryhmät voivat limittyä. Rahoitusmuoto ja ennakkotieto eivät ole avoimia hakuja. Kelpoisuutta tai ehtojen täydellisyyttä ei ole vahvistettu."}
