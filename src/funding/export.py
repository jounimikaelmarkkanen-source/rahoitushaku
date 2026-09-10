import csv
import gzip
import hashlib
import io
import json
from html import escape
from pathlib import Path

from sqlalchemy import MetaData, select, text

from funding.documents import document_response_issue
from funding.domain import dump, now
from funding.models import (
    Base,
    Document,
    DocumentBlob,
    DocumentLink,
    DocumentVersion,
    Lease,
    Opportunity,
    OpportunityDocument,
)
from funding.query import funding_view, health


def safe_cell(value):
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + value
    return value


def csv_text(rows, fields):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({key: safe_cell(value) for key, value in row.items()})
    return stream.getvalue()


def export_data(engine, factory, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    view = funding_view(engine)
    with engine.connect() as conn:
        rows = [dict(r) for r in conn.execute(select(view).order_by(view.c.id)).mappings()]
        revision = conn.scalar(text("SELECT version_num FROM alembic_version"))
    (directory / "opportunities.jsonl").write_text("".join(dump(r) + "\n" for r in rows), encoding="utf-8")
    (directory / "opportunities.csv").write_text(csv_text(rows, list(view.c.keys())), encoding="utf-8-sig")
    sources = health(factory)
    (directory / "sources.json").write_text(dump(sources) + "\n", encoding="utf-8")
    documents = export_documents(engine, directory)
    (directory / "manifest.json").write_text(dump({"schema_version": revision, "exported_at_utc": now(), "opportunities": len(rows), "source_count": len(sources), "format": "UTF-8 JSONL / UTF-8 BOM CSV", "csv_formula_escape": True,
        "documents": documents, "full_content_location": "documents/originals + documents/texts; also stored in database",
        "completeness_verified": False})+"\n", encoding="utf-8")
    return len(rows)


def original_extension(media_type):
    return {"application/pdf": ".pdf", "application/json": ".json", "text/html": ".html",
            "text/plain": ".txt", "application/zip": ".zip", "application/msword": ".doc",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
            "application/vnd.oasis.opendocument.text": ".odt", "application/xml": ".xml",
            "application/vnd.oasis.opendocument.spreadsheet": ".ods",
            "application/vnd.oasis.opendocument.presentation": ".odp",
            "application/vnd.ms-word.document.macroenabled.12": ".docm",
            "application/vnd.ms-excel.sheet.macroenabled.12": ".xlsm",
            "application/vnd.ms-powerpoint.presentation.macroenabled.12": ".pptm",
            "application/vnd.ms-powerpoint": ".ppt",
            "text/xml": ".xml", "application/vnd.ms-excel": ".xls", "image/png": ".png",
            "image/jpeg": ".jpg", "application/rtf": ".rtf"}.get(media_type.lower(), ".bin")


def extraction_notes(flags):
    notes = []
    for flag in flags:
        if flag.startswith("pages_need_visual_or_ocr_review:"):
            notes.append("Tarkista alkuperäisestä sivut "+flag.split(":", 1)[1]+".")
        elif flag == "ocr_text_requires_human_verification":
            notes.append("Tekstiä on tunnistettu kuvista. Tarkista luvut ja ehdot alkuperäisestä tiedostosta.")
        elif flag.startswith("ocr_page_limit:"):
            notes.append("Kuvista tunnistettavien sivujen keruuraja on "+flag.split(":", 1)[1]+" sivua.")
        elif flag == "full_eu_conditions_not_present_in_source_entry":
            notes.append("Julkaisijan hakutietueesta puuttuu varsinainen sisältöteksti.")
        elif flag == "full_faq_question_or_answer_not_published":
            notes.append("Julkaisijan FAQ-tietueesta puuttuu kysymys tai vastaus.")
        elif flag == "document_download_returned_html":
            notes.append("Asiakirjalinkki palautti verkkosivun. Varsinaista liitetiedostoa ei saatu.")
        elif flag == "office_layout_and_embedded_objects_need_review":
            notes.append("Tarkista asettelu, kuvat ja laskentataulukot alkuperäisestä Office-tiedostosta.")
        elif flag in ("unsupported_format_original_retained", "archive_requires_manual_extraction", "encrypted_pdf"):
            notes.append("Alkuperäinen tiedosto on tallennettu, mutta sen kokotekstiä ei voitu poimia.")
    return notes


def export_documents(engine, directory):
    """Stream lossless originals, full texts, associations and history as portable files."""
    directory = Path(directory)/"documents"
    originals, texts = directory/"originals", directory/"texts"
    originals.mkdir(parents=True, exist_ok=True)
    texts.mkdir(parents=True, exist_ok=True)
    count = 0
    with engine.connect() as conn:
        for model, filename in ((Document, "documents.jsonl"), (OpportunityDocument, "opportunity-documents.jsonl"),
                                (DocumentLink, "links.jsonl"), (DocumentVersion, "versions.jsonl")):
            with (directory/filename).open("w", encoding="utf-8") as stream:
                for row in conn.execute(select(model.__table__)).mappings():
                    stream.write(dump(dict(row))+"\n")
        with (directory/"contents.jsonl").open("w", encoding="utf-8") as index:
            for row in conn.execute(select(DocumentBlob.__table__)).mappings():
                data = dict(row)
                body = gzip.decompress(data.pop("original_gzip"))
                if hashlib.sha256(body).hexdigest() != data["sha256"]:
                    raise ValueError("Document checksum mismatch during export")
                filename = data["sha256"]+original_extension(data["media_type"])
                (originals/filename).write_bytes(body)
                (texts/(data["sha256"]+".txt")).write_text(data.pop("text"), encoding="utf-8")
                data.update(original_file="originals/"+filename, text_file="texts/"+data["sha256"]+".txt")
                index.write(dump(data)+"\n")
                count += 1
        calls = directory/"calls"
        calls.mkdir(exist_ok=True)
        stmt = select(Opportunity.id, Opportunity.title, Document.id.label("document_id"), Document.title.label("document_title"), Document.url, Document.final_url,
                      Document.state, Document.current_sha256, DocumentBlob.media_type, Document.extraction_status,
                      DocumentBlob.flags_json,
                      Document.last_success_at, OpportunityDocument.role, OpportunityDocument.limitation, Document.error).outerjoin(
            OpportunityDocument, (OpportunityDocument.opportunity_id == Opportunity.id)
            & (OpportunityDocument.active == True)).outerjoin(  # noqa: E712
            Document, Document.id == OpportunityDocument.document_id).outerjoin(
            DocumentBlob, DocumentBlob.sha256 == Document.current_sha256).order_by(Opportunity.id, OpportunityDocument.depth, Document.url)
        stream, previous = None, None
        states = {"pending": "Odottaa keruuta", "fetched": "Tallennettu", "failed": "Lataus epäonnistui", "blocked": "Lähteen käyttörajoitus"}
        extraction = {"extracted": "Teksti poimittu", "partial_text": "Teksti tarkistettava", "unreadable": "Kokoteksti puuttuu", "not_extracted": "Tekstiä ei vielä poimittu"}
        def finish():
            if stream:
                stream.write("</main></body></html>")
                stream.close()
        try:
            for row in conn.execute(stmt).mappings():
                if row["id"] != previous:
                    finish()
                    stream = (calls/(row["id"]+".html")).open("w", encoding="utf-8")
                    stream.write('<!doctype html><html lang="fi"><head><meta charset="utf-8">'
                        '<meta name="viewport" content="width=device-width,initial-scale=1">'
                        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; base-uri \'none\'; form-action \'none\'">'
                        '<title>'+escape(row["title"])+" · Rahoitusrekisteri</title><style>"
                        'body{margin:0;background:#f3f6f6;color:#163d49;font:17px/1.6 system-ui,sans-serif}'
                        'main{max-width:980px;margin:auto;padding:36px 24px}h1{font-size:30px;line-height:1.25;overflow-wrap:anywhere}'
                        'h2{font-size:19px;overflow-wrap:anywhere}article{background:white;border:1px solid #d4dfe0;border-radius:10px;padding:20px;margin:18px 0}'
                        'a{color:#076b78;overflow-wrap:anywhere}a:focus{outline:3px solid #b75c0b}'
                        '.note{background:#fff1db;padding:16px;border-left:4px solid #b75c0b;overflow-wrap:anywhere}.meta{font-size:14px;color:#476069}.actions a{margin-right:24px}'
                        '</style></head><body><main><p class="meta">RAHOITUSREKISTERI · EHDOT JA LISÄTIEDOT</p><h1>'+escape(row["title"])+"</h1>"
                        '<p class="note">Aineiston kattavuutta ei ole vahvistettu asiantuntijatyönä. Tarkista alla näkyvät puutteet. '
                        'Lue kokoteksti ja tarkista ehdot alkuperäisistä asiakirjoista ennen hakemista.</p>')
                    previous = row["id"]
                if row["document_id"] is None:
                    stream.write('<p class="note">Asiakirjojen keruuta ei ole vielä aloitettu.</p>')
                    continue
                stream.write('<article><h2>'+escape(row["document_title"] or row["url"])+"</h2><p>"
                             +states.get(row["state"], row["state"])+" · "+extraction.get(row["extraction_status"], "Tekstiä ei vielä poimittu")+"</p>")
                url = escape(row["url"], quote=True)
                stream.write('<p class="meta">Lähde: <a rel="noreferrer noopener" href="'+url+'">'+url+'</a><br>Viimeisin onnistunut keruu (UTC): '
                             +escape(row["last_success_at"].strftime("%d.%m.%Y %H.%M") if row["last_success_at"] else "Ei onnistunutta latausta")+"</p>")
                if row["current_sha256"]:
                    sha = row["current_sha256"]
                    response_only = document_response_issue(row["url"], row["media_type"], row["final_url"])
                    text_label = "Lue palvelun vastauksen teksti" if response_only else "Lue koko teksti"
                    file_label = "Lataa palvelun vastaus" if response_only else "Lataa alkuperäinen tiedosto"
                    stream.write(f'<p class="actions"><a href="../texts/{sha}.txt">{text_label}</a>'
                                 f'<a download href="../originals/{sha}{original_extension(row["media_type"])}">{file_label}</a></p>')
                if row["error"] or row["limitation"]:
                    issue = str(row["error"] or row["limitation"])
                    if issue == "DOCUMENT_DOWNLOAD_RETURNED_HTML":
                        issue = "Asiakirjalinkki palautti verkkosivun. Varsinaista liitetiedostoa ei saatu."
                    if issue == "DETAIL_REDIRECTED_TO_FRONT_PAGE":
                        issue = "Lisätietolinkki ohjasi etusivulle. Pyydettyä ohjetta tai sisältösivua ei saatu."
                    if issue.startswith("RATE_LIMIT|"):
                        _, origin, stamp = issue.split("|", 2)
                        issue = f"Lähde rajoittaa pyyntöjä ({origin}). Keruu voi jatkua aikaisintaan {stamp} UTC."
                    stream.write('<p class="note">Puute: '+escape(issue)+"</p>")
                for note in extraction_notes(json.loads(row["flags_json"] or "[]")):
                    stream.write('<p class="note">'+escape(note)+"</p>")
                stream.write("</article>\n")
        finally:
            finish()
    return count


def transfer_database(source_engine, target_engine):
    """Lossless relational transfer to an empty, migrated database (including provenance)."""
    # Both sides must already have exactly the same schema revision.
    from sqlalchemy import text
    with source_engine.connect() as src, target_engine.begin() as dst:
        if src.execute(select(Lease.__table__).where(Lease.expires_at > now())).first():
            raise ValueError("Stop the active collector before transferring the database")
        if src.scalar(text("SELECT version_num FROM alembic_version")) != dst.scalar(text("SELECT version_num FROM alembic_version")):
            raise ValueError("Database schema versions differ")
        metadata = MetaData()
        metadata.reflect(bind=source_engine, only=list(Base.metadata.tables))
        # Refuse rather than erase any existing destination data.
        for table in metadata.sorted_tables:
            if dst.execute(select(table).limit(1)).first():
                raise ValueError(f"Destination table is not empty: {table.name}")
        for table in metadata.sorted_tables:
            if table.name == "leases":
                continue
            target_table = Base.metadata.tables[table.name]
            for chunk in src.execute(select(table)).mappings().partitions(1 if table.name in ("document_blobs", "page_snapshots") else 500):
                # SQLAlchemy's SQL Server dialect enables IDENTITY_INSERT when explicit IDs are provided.
                dst.execute(target_table.insert(), [dict(row) for row in chunk])
