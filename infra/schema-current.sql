-- Schema revision 0007; use only for an empty database.
-- Normally run alembic upgrade head instead.

CREATE TABLE sources (
	id VARCHAR(80) NOT NULL,
	name NVARCHAR(300) NOT NULL,
	url NVARCHAR(2048) NOT NULL,
	adapter VARCHAR(40) NOT NULL,
	category NVARCHAR(100) NOT NULL,
	coverage NVARCHAR(max) NOT NULL,
	owner NVARCHAR(200) NOT NULL,
	enabled BIT NOT NULL,
	config_json NVARCHAR(max) NOT NULL,
	last_attempt_at DATETIME NULL,
	last_success_at DATETIME NULL,
	health VARCHAR(30) NOT NULL,
	last_error NVARCHAR(max) NULL,
	PRIMARY KEY (id)
)
GO

CREATE TABLE leases (
	name VARCHAR(100) NOT NULL,
	owner VARCHAR(36) NOT NULL,
	expires_at DATETIME NOT NULL,
	PRIMARY KEY (name)
)
GO

CREATE TABLE document_blobs (
	sha256 VARCHAR(64) NOT NULL,
	original_gzip VARBINARY(max) NOT NULL,
	byte_count INTEGER NOT NULL,
	media_type VARCHAR(200) NOT NULL,
	text NVARCHAR(max) NOT NULL,
	extraction_status VARCHAR(40) NOT NULL,
	flags_json NVARCHAR(max) NOT NULL,
	page_count INTEGER NULL,
	created_at DATETIME NOT NULL,
	PRIMARY KEY (sha256)
)
GO

CREATE TABLE collection_runs (
	id VARCHAR(36) NOT NULL,
	source_id VARCHAR(80) NOT NULL,
	started_at DATETIME NOT NULL,
	finished_at DATETIME NULL,
	status VARCHAR(30) NOT NULL,
	seen INTEGER NOT NULL,
	changed INTEGER NOT NULL,
	rejected INTEGER NOT NULL,
	expected INTEGER NULL,
	message NVARCHAR(max) NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(source_id) REFERENCES sources (id)
)
GO

CREATE INDEX ix_collection_runs_source_id ON collection_runs (source_id)
GO

CREATE TABLE opportunities (
	id VARCHAR(36) NOT NULL,
	source_id VARCHAR(80) NOT NULL,
	external_id NVARCHAR(400) NOT NULL,
	canonical_url NVARCHAR(2048) NOT NULL,
	title NVARCHAR(1000) NOT NULL,
	description NVARCHAR(max) NOT NULL,
	funder NVARCHAR(500) NOT NULL,
	programme NVARCHAR(200) NOT NULL,
	record_kind VARCHAR(30) NOT NULL DEFAULT 'call',
	instrument VARCHAR(40) NOT NULL,
	language VARCHAR(10) NOT NULL,
	source_status VARCHAR(30) NOT NULL,
	opens_on DATETIME NULL,
	deadline_on DATETIME NULL,
	deadline_at DATETIME NULL,
	deadline_expires_at DATETIME NULL,
	deadline_model VARCHAR(40) NOT NULL,
	total_budget NUMERIC(20, 2) NULL,
	grant_max NUMERIC(20, 2) NULL,
	funding_rate NUMERIC(5, 2) NULL,
	currency VARCHAR(3) NULL,
	eligibility_text NVARCHAR(max) NOT NULL,
	geographic_scope VARCHAR(30) NOT NULL,
	detail_level VARCHAR(30) NOT NULL,
	quality_flags_json NVARCHAR(max) NOT NULL,
	content_hash VARCHAR(64) NOT NULL,
	version INTEGER NOT NULL,
	first_seen_at DATETIME NOT NULL,
	last_seen_at DATETIME NOT NULL,
	updated_at DATETIME NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(source_id) REFERENCES sources (id)
)
GO

CREATE INDEX ix_opportunities_updated_at ON opportunities (updated_at)
GO

CREATE INDEX ix_opportunities_deadline_on ON opportunities (deadline_on)
GO

CREATE INDEX ix_opportunities_record_kind ON opportunities (record_kind)
GO

CREATE INDEX ix_opportunities_programme ON opportunities (programme)
GO

CREATE INDEX ix_opportunities_source_id ON opportunities (source_id)
GO

CREATE INDEX ix_opportunities_geographic_scope ON opportunities (geographic_scope)
GO

CREATE INDEX ix_opportunities_instrument ON opportunities (instrument)
GO

CREATE INDEX ix_opportunities_funder ON opportunities (funder)
GO

CREATE TABLE page_snapshots (
	id VARCHAR(64) NOT NULL,
	source_id VARCHAR(80) NOT NULL,
	url NVARCHAR(2048) NOT NULL,
	text_hash VARCHAR(64) NOT NULL,
	text NVARCHAR(max) NOT NULL,
	html_gzip VARBINARY(max) NOT NULL,
	first_seen_at DATETIME NOT NULL,
	last_seen_at DATETIME NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(source_id) REFERENCES sources (id)
)
GO

CREATE INDEX ix_page_snapshots_source_id ON page_snapshots (source_id)
GO

CREATE TABLE documents (
	id VARCHAR(64) NOT NULL,
	url NVARCHAR(2048) NOT NULL,
	final_url NVARCHAR(2048) NULL,
	parser VARCHAR(40) NOT NULL,
	state VARCHAR(40) NOT NULL,
	extraction_status VARCHAR(40) NOT NULL DEFAULT 'not_extracted',
	current_sha256 VARCHAR(64) NULL,
	title NVARCHAR(1000) NOT NULL,
	checked_at DATETIME NULL,
	last_success_at DATETIME NULL,
	next_check_at DATETIME NULL,
	http_status INTEGER NULL,
	attempts INTEGER NOT NULL,
	error NVARCHAR(max) NULL,
	etag NVARCHAR(500) NULL,
	last_modified NVARCHAR(100) NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(current_sha256) REFERENCES document_blobs (sha256)
)
GO

CREATE INDEX ix_documents_current_sha256 ON documents (current_sha256)
GO

CREATE INDEX ix_documents_state ON documents (state)
GO

CREATE INDEX ix_documents_next_check_at ON documents (next_check_at)
GO

CREATE TABLE source_items (
	id VARCHAR(64) NOT NULL,
	source_id VARCHAR(80) NOT NULL,
	external_id NVARCHAR(400) NOT NULL,
	opportunity_id VARCHAR(36) NOT NULL,
	raw_json NVARCHAR(max) NOT NULL,
	raw_hash VARCHAR(64) NOT NULL,
	last_seen_at DATETIME NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(source_id) REFERENCES sources (id),
	FOREIGN KEY(opportunity_id) REFERENCES opportunities (id)
)
GO

CREATE INDEX ix_source_items_opportunity_id ON source_items (opportunity_id)
GO

CREATE INDEX ix_source_items_source_id ON source_items (source_id)
GO

CREATE TABLE opportunity_tags (
	opportunity_id VARCHAR(36) NOT NULL,
	kind VARCHAR(30) NOT NULL,
	value NVARCHAR(200) NOT NULL,
	basis VARCHAR(30) NOT NULL,
	PRIMARY KEY (opportunity_id, kind, value),
	FOREIGN KEY(opportunity_id) REFERENCES opportunities (id)
)
GO

CREATE INDEX ix_tag_lookup ON opportunity_tags (kind, value)
GO

CREATE TABLE deadlines (
	opportunity_id VARCHAR(36) NOT NULL,
	stage INTEGER NOT NULL,
	due_on DATETIME NOT NULL,
	due_at DATETIME NULL,
	original NVARCHAR(100) NOT NULL,
	timezone VARCHAR(60) NOT NULL,
	PRIMARY KEY (opportunity_id, stage),
	FOREIGN KEY(opportunity_id) REFERENCES opportunities (id)
)
GO

CREATE INDEX ix_deadlines_due_on ON deadlines (due_on)
GO

CREATE TABLE changes (
	id INTEGER NOT NULL IDENTITY,
	opportunity_id VARCHAR(36) NULL,
	source_id VARCHAR(80) NOT NULL,
	kind VARCHAR(40) NOT NULL,
	created_at DATETIME NOT NULL,
	payload_json NVARCHAR(max) NOT NULL,
	raw_json NVARCHAR(max) NULL,
	actor NVARCHAR(200) NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(opportunity_id) REFERENCES opportunities (id),
	FOREIGN KEY(source_id) REFERENCES sources (id)
)
GO

CREATE INDEX ix_changes_opportunity_id ON changes (opportunity_id)
GO

CREATE INDEX ix_changes_created_at ON changes (created_at)
GO

CREATE TABLE reviews (
	opportunity_id VARCHAR(36) NOT NULL,
	eligibility VARCHAR(30) NOT NULL,
	city_role VARCHAR(30) NOT NULL,
	service_area NVARCHAR(200) NOT NULL,
	notes NVARCHAR(max) NOT NULL,
	evidence_url NVARCHAR(2048) NOT NULL,
	reviewed_source_version INTEGER NOT NULL,
	version INTEGER NOT NULL,
	updated_at DATETIME NOT NULL,
	updated_by NVARCHAR(200) NOT NULL,
	PRIMARY KEY (opportunity_id),
	FOREIGN KEY(opportunity_id) REFERENCES opportunities (id)
)
GO

CREATE TABLE rejected_items (
	id INTEGER NOT NULL IDENTITY,
	run_id VARCHAR(36) NOT NULL,
	reason NVARCHAR(max) NOT NULL,
	raw_json NVARCHAR(max) NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(run_id) REFERENCES collection_runs (id)
)
GO

CREATE TABLE document_versions (
	document_id VARCHAR(64) NOT NULL,
	sha256 VARCHAR(64) NOT NULL,
	first_seen_at DATETIME NOT NULL,
	last_seen_at DATETIME NOT NULL,
	PRIMARY KEY (document_id, sha256),
	FOREIGN KEY(document_id) REFERENCES documents (id),
	FOREIGN KEY(sha256) REFERENCES document_blobs (sha256)
)
GO

CREATE TABLE document_links (
	id VARCHAR(64) NOT NULL,
	document_id VARCHAR(64) NOT NULL,
	source_sha256 VARCHAR(64) NOT NULL,
	target_url NVARCHAR(2048) NOT NULL,
	title NVARCHAR(1000) NOT NULL,
	role VARCHAR(40) NOT NULL,
	follow BIT NOT NULL,
	parser VARCHAR(40) NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(document_id) REFERENCES documents (id),
	FOREIGN KEY(source_sha256) REFERENCES document_blobs (sha256)
)
GO

CREATE INDEX ix_document_links_document_id ON document_links (document_id)
GO

CREATE TABLE opportunity_documents (
	opportunity_id VARCHAR(36) NOT NULL,
	document_id VARCHAR(64) NOT NULL,
	parent_document_id VARCHAR(64) NULL,
	role VARCHAR(40) NOT NULL,
	depth INTEGER NOT NULL,
	is_root BIT NOT NULL,
	active BIT NOT NULL,
	limitation VARCHAR(40) NULL,
	first_seen_at DATETIME NOT NULL,
	PRIMARY KEY (opportunity_id, document_id),
	FOREIGN KEY(opportunity_id) REFERENCES opportunities (id),
	FOREIGN KEY(document_id) REFERENCES documents (id),
	FOREIGN KEY(parent_document_id) REFERENCES documents (id)
)
GO

CREATE INDEX ix_opportunity_documents_lookup ON opportunity_documents (document_id, active, opportunity_id)
GO

CREATE VIEW v_document_coverage AS
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
        GROUP BY od.opportunity_id
GO

CREATE VIEW v_funding_documents AS SELECT od.*, d.url, d.final_url, d.title,
        d.state, d.parser, d.checked_at, d.last_success_at, d.http_status, d.error, d.current_sha256,
        b.media_type, b.byte_count, b.text AS full_text, d.extraction_status, b.flags_json, b.page_count
        FROM opportunity_documents od JOIN documents d ON od.document_id=d.id
        LEFT JOIN document_blobs b ON d.current_sha256=b.sha256
GO

CREATE VIEW v_funding AS SELECT o.*,
        CASE
 WHEN o.source_status = 'cancelled' THEN 'cancelled'
 WHEN o.deadline_expires_at IS NOT NULL AND o.deadline_expires_at <= SYSUTCDATETIME() THEN 'closed'
 WHEN o.deadline_at IS NOT NULL AND o.deadline_at < SYSUTCDATETIME() THEN 'closed'
 WHEN o.deadline_on IS NOT NULL AND o.deadline_on < CAST(SYSUTCDATETIME() AS DATE) THEN 'closed'
 WHEN o.source_status = 'closed' THEN 'closed'
 WHEN o.opens_on IS NOT NULL AND o.opens_on > CAST(SYSUTCDATETIME() AS DATE) THEN 'forthcoming'
 ELSE o.source_status END AS effective_status,
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
        LEFT JOIN v_document_coverage c ON c.opportunity_id=o.id
GO

CREATE VIEW v_funding_tags AS SELECT opportunity_id, kind, value, basis FROM opportunity_tags
GO

CREATE VIEW v_source_health AS SELECT id, name, category, adapter, enabled, health, last_attempt_at, last_success_at, last_error, coverage FROM sources
GO

CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)
GO

INSERT INTO alembic_version (version_num) VALUES ('0007')
GO
