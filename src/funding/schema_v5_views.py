"""Frozen migration 0005: coverage without large-body joins."""
STATUS_SQL = """CASE
 WHEN o.source_status = 'cancelled' THEN 'cancelled'
 WHEN o.deadline_expires_at IS NOT NULL AND o.deadline_expires_at <= CURRENT_TIMESTAMP THEN 'closed'
 WHEN o.deadline_at IS NOT NULL AND o.deadline_at < CURRENT_TIMESTAMP THEN 'closed'
 WHEN o.deadline_on IS NOT NULL AND o.deadline_on < CAST(CURRENT_TIMESTAMP AS DATE) THEN 'closed'
 WHEN o.source_status = 'closed' THEN 'closed'
 WHEN o.opens_on IS NOT NULL AND o.opens_on > CAST(CURRENT_TIMESTAMP AS DATE) THEN 'forthcoming'
 ELSE o.source_status END"""


def view_statements(dialect):
    status = STATUS_SQL
    if dialect == "sqlite":
        status = status.replace("CAST(CURRENT_TIMESTAMP AS DATE)", "DATE(CURRENT_TIMESTAMP)")
    elif dialect == "mssql":
        status = status.replace("CURRENT_TIMESTAMP", "SYSUTCDATETIME()")
    yield """CREATE VIEW v_document_coverage AS
        SELECT od.opportunity_id,
        COUNT(*) AS document_count,
        SUM(CASE WHEN d.state='fetched' THEN 1 ELSE 0 END) AS fetched_count,
        SUM(CASE WHEN d.state='pending' THEN 1 ELSE 0 END) AS pending_count,
        SUM(CASE WHEN d.state IN ('failed','blocked') THEN 1 ELSE 0 END) AS failed_count,
        SUM(CASE WHEN d.state='fetched' AND d.extraction_status <> 'extracted' THEN 1 ELSE 0 END) AS text_issue_count,
        SUM(CASE WHEN od.limitation IS NOT NULL THEN 1 ELSE 0 END) AS limited_count,
        SUM(CASE WHEN od.is_root=1 THEN 1 ELSE 0 END) AS root_count,
        SUM(CASE WHEN od.is_root=1 AND d.state='fetched' AND d.extraction_status='extracted' THEN 1 ELSE 0 END) AS roots_fetched,
        MIN(d.last_success_at) AS oldest_document_at,
        MAX(d.checked_at) AS documents_checked_at
        FROM opportunity_documents od JOIN documents d ON od.document_id=d.id
        WHERE od.active=1
        GROUP BY od.opportunity_id"""
    yield """CREATE VIEW v_funding_documents AS SELECT od.*, d.url, d.final_url, d.title,
        d.state, d.parser, d.checked_at, d.last_success_at, d.http_status, d.error, d.current_sha256,
        b.media_type, b.byte_count, b.text AS full_text, b.extraction_status, b.flags_json, b.page_count
        FROM opportunity_documents od JOIN documents d ON od.document_id=d.id
        LEFT JOIN document_blobs b ON d.current_sha256=b.sha256"""
    yield f"""CREATE VIEW v_funding AS SELECT o.*,
        {status} AS effective_status,
        COALESCE(r.eligibility, 'unreviewed') AS eligibility,
        COALESCE(r.city_role, 'unknown') AS city_role,
        COALESCE(r.service_area, '') AS service_area,
        COALESCE(r.notes, '') AS review_notes,
        CASE WHEN r.opportunity_id IS NULL OR r.eligibility = 'unreviewed' OR r.reviewed_source_version <> o.version THEN 1 ELSE 0 END AS needs_review,
        s.name AS source_name, s.health AS source_health, s.last_success_at AS source_last_success_at,
        CASE WHEN c.opportunity_id IS NULL THEN 'not_started'
          WHEN c.failed_count>0 OR c.text_issue_count>0 OR c.limited_count>0 THEN 'partial'
          WHEN c.pending_count>0 THEN 'in_progress'
          ELSE 'collected_unverified' END AS content_state,
        COALESCE(c.document_count,0) AS document_count, COALESCE(c.fetched_count,0) AS fetched_count,
        COALESCE(c.pending_count,0) AS pending_document_count, COALESCE(c.failed_count,0) AS failed_document_count,
        COALESCE(c.text_issue_count,0) AS document_text_issues, COALESCE(c.limited_count,0) AS limited_document_count,
        COALESCE(c.root_count,0) AS root_document_count, COALESCE(c.roots_fetched,0) AS root_documents_fetched,
        c.oldest_document_at, c.documents_checked_at
        FROM opportunities o JOIN sources s ON s.id=o.source_id
        LEFT JOIN reviews r ON r.opportunity_id=o.id
        LEFT JOIN v_document_coverage c ON c.opportunity_id=o.id"""
    yield "CREATE VIEW v_funding_tags AS SELECT opportunity_id, kind, value, basis FROM opportunity_tags"
    yield "CREATE VIEW v_source_health AS SELECT id, name, category, adapter, enabled, health, last_attempt_at, last_success_at, last_error, coverage FROM sources"
