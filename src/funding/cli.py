import argparse
import json
import logging
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine

from funding.collector import collect, sync_sources, upsert
from funding.db import make_engine, sessions
from funding.documents import coverage, enrich_documents, reextract_documents
from funding.domain import Record, dump
from funding.export import export_data, transfer_database
from funding.query import health
from funding.settings import settings


def main():
    parser = argparse.ArgumentParser(description="Kuntien ulkoisen rahoituksen rekisteri")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init", help="Migrate database and register configured sources")
    sub.add_parser("sync-sources", help="Update source registry after a configuration change")
    run = sub.add_parser("collect", help="Collect enabled sources once; job scheduler runs this daily")
    run.add_argument("--source", action="append")
    run.add_argument("--require-all", action="store_true", help="Return nonzero if any source is incomplete")
    enrich = sub.add_parser("enrich", help="Collect full call content and linked terms/attachments; resumable")
    enrich.add_argument("--source", action="append")
    enrich.add_argument("--workers", type=int, default=6, choices=range(1, 13))
    enrich.add_argument("--max-fetches", type=int, default=0, help="Zero means process all due documents")
    enrich.add_argument("--max-depth", type=int, default=4)
    enrich.add_argument("--max-documents", type=int, default=250)
    enrich.add_argument("--retry-failed", action="store_true")
    enrich.add_argument("--pending-only", action="store_true", help="Finish newly discovered documents without refreshing fetched originals")
    enrich.add_argument("--current-only", action="store_true", help="Finish current and unknown-status calls; skip expired and cancelled history")
    sub.add_parser("coverage", help="Report actual full-content and attachment coverage")
    faq = sub.add_parser("faq", help="Archive public EU FAQ answers and link exact topic keywords")
    faq.add_argument("--from-dir", type=Path, help="Import a previously collected FAQ snapshot")
    reextract = sub.add_parser("reextract", help="Rebuild full text/OCR from archived originals; no network requests")
    reextract.add_argument("--parser", action="append")
    reextract.add_argument("--issues-only", action="store_true")
    reextract.add_argument("--document-id", action="append", help="Rebuild only the selected archived document IDs")
    daily = sub.add_parser("daily", help="Collect catalogues and enrich content even when one catalogue fails")
    daily.add_argument("--require-all", action="store_true")
    report = sub.add_parser("health")
    report.add_argument("--check", action="store_true", help="Nonzero when an enabled source failed or is stale")
    export = sub.add_parser("export")
    export.add_argument("--out", type=Path, default=Path("outputs/data"))
    manual = sub.add_parser("import", help="Import reviewed public notices from a JSONL file")
    manual.add_argument("path", type=Path)
    transfer = sub.add_parser("transfer", help="Copy all tables into an empty migrated destination")
    transfer.add_argument("--target-url", help="Destination SQLAlchemy URL; prefer FUNDING_AZURE_SQL_SERVER for Azure")
    transfer.add_argument("--from-url", required=True)
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING)
    cfg = settings()
    if args.command == "init":
        command.upgrade(Config("alembic.ini"), "head")
    engine = make_engine(cfg)
    factory = sessions(engine)
    if args.command in ("init", "sync-sources"):
        sync_sources(factory, cfg.source_file)
        print("Database migrated; source registry updated.")
    elif args.command == "collect":
        outcomes = collect(factory, cfg, args.source)
        if args.require_all and any(o["status"] != "success" for o in outcomes):
            sys.exit(2)
    elif args.command == "enrich":
        if args.max_fetches < 0 or args.max_depth < 0 or args.max_documents < 1:
            parser.error("Document limits must be nonnegative; max-documents must be positive")
        enrich_documents(factory, cfg, args.source, args.workers, args.max_fetches,
                         args.max_depth, args.max_documents, args.retry_failed, pending_only=args.pending_only,
                         current_only=args.current_only)
    elif args.command == "coverage":
        print(dump(coverage(factory)))
    elif args.command == "faq":
        from funding.eu_faq import collect_faq
        print(dump(collect_faq(factory, cfg, args.from_dir)))
    elif args.command == "reextract":
        print(dump(reextract_documents(factory, args.parser, args.issues_only, args.document_id)))
    elif args.command == "daily":
        from funding.eu_faq import collect_faq
        outcomes = collect(factory, cfg)
        try:
            faq_result = collect_faq(factory, cfg)
            print(dump({"faq": faq_result}), flush=True)
        except Exception as exc:
            faq_result = {"status": "failed", "error": str(exc)}
            print(dump({"faq": faq_result}), flush=True)
        result = enrich_documents(factory, cfg)
        if args.require_all and (any(o["status"] != "success" for o in outcomes)
                                 or faq_result["status"] not in ("success", "cached")
                                 or any(result["current_documents"].get(s, 0) for s in ("pending", "failed", "blocked"))
                                 or any(result["calls"].get(s, 0) for s in ("not_started", "in_progress", "partial"))):
            sys.exit(2)
    elif args.command == "health":
        data = health(factory, cfg.stale_hours)
        print(dump(data))
        if args.check and any(s["enabled"] and (s["health"] != "success" or s["stale"]) for s in data):
            sys.exit(2)
    elif args.command == "export":
        print(dump({"exported": export_data(engine, factory, args.out), "directory": str(args.out)}))
    elif args.command == "import":
        records = [json.loads(line) for line in args.path.read_text().splitlines() if line.strip()]
        parsed = [Record.model_validate(r) for r in records]
        with factory.begin() as session:
            for record, raw in zip(parsed, records, strict=True):
                upsert(session, "manual", record, raw)
        print(dump({"imported": len(parsed)}))
    elif args.command == "transfer":
        target = create_engine(args.target_url) if args.target_url else engine
        transfer_database(create_engine(args.from_url), target)
        print("All tables transferred in a single destination transaction.")


if __name__ == "__main__":
    main()
