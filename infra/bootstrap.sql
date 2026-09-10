-- Run as an Entra SQL administrator against the migrated 'funding' database.
-- Replace identity names and the 0x placeholders with SIDs produced by scripts/sql_principals.py.
-- CREATE USER ... SID / TYPE avoids requiring Microsoft Graph Directory Readers permissions.
CREATE USER [funding-collector] WITH SID = 0xCOLLECTOR_SID, TYPE = E;
CREATE USER [funding-api] WITH SID = 0xAPI_SID, TYPE = E;
CREATE ROLE funding_reader;
GRANT SELECT ON dbo.v_funding TO funding_reader;
GRANT SELECT ON dbo.v_funding_tags TO funding_reader;
GRANT SELECT ON dbo.v_source_health TO funding_reader;
GRANT SELECT ON dbo.v_funding_documents TO funding_reader;
GRANT SELECT ON dbo.v_document_coverage TO funding_reader;
GRANT SELECT ON dbo.documents TO funding_reader;
GRANT SELECT ON dbo.document_blobs TO funding_reader;
GRANT SELECT ON dbo.document_versions TO funding_reader;
GRANT SELECT ON dbo.document_links TO funding_reader;
GRANT SELECT ON dbo.opportunity_documents TO funding_reader;
GRANT SELECT ON dbo.deadlines TO funding_reader;

-- Collector has data rights only. Migrations always use a separate deployment identity.
GRANT SELECT, INSERT, UPDATE ON dbo.sources TO [funding-collector];
GRANT SELECT, INSERT, UPDATE ON dbo.collection_runs TO [funding-collector];
GRANT SELECT, INSERT, UPDATE ON dbo.opportunities TO [funding-collector];
GRANT SELECT, INSERT, UPDATE ON dbo.source_items TO [funding-collector];
GRANT SELECT, INSERT, UPDATE, DELETE ON dbo.opportunity_tags TO [funding-collector];
GRANT SELECT, INSERT, UPDATE, DELETE ON dbo.deadlines TO [funding-collector];
GRANT SELECT, INSERT ON dbo.changes TO [funding-collector];
GRANT SELECT, INSERT, UPDATE ON dbo.page_snapshots TO [funding-collector];
GRANT SELECT, INSERT ON dbo.rejected_items TO [funding-collector];
GRANT SELECT, INSERT, UPDATE, DELETE ON dbo.leases TO [funding-collector];
GRANT SELECT ON dbo.v_funding TO [funding-collector];
GRANT SELECT ON dbo.v_document_coverage TO [funding-collector];
GRANT SELECT, INSERT, UPDATE ON dbo.documents TO [funding-collector];
GRANT SELECT, INSERT ON dbo.document_blobs TO [funding-collector];
GRANT UPDATE (text, extraction_status, flags_json, page_count, media_type) ON dbo.document_blobs TO [funding-collector];
GRANT SELECT, INSERT, UPDATE ON dbo.document_versions TO [funding-collector];
GRANT SELECT, INSERT, UPDATE ON dbo.document_links TO [funding-collector];
GRANT SELECT, INSERT, UPDATE ON dbo.opportunity_documents TO [funding-collector];

ALTER ROLE funding_reader ADD MEMBER [funding-api];
GRANT SELECT ON dbo.opportunities TO [funding-api];
GRANT SELECT ON dbo.sources TO [funding-api];
GRANT SELECT ON dbo.source_items TO [funding-api];
GRANT SELECT ON dbo.opportunity_tags TO [funding-api];
GRANT SELECT ON dbo.page_snapshots TO [funding-api];
GRANT SELECT ON dbo.collection_runs TO [funding-api];
GRANT SELECT ON dbo.alembic_version TO [funding-api];
GRANT SELECT, INSERT, UPDATE ON dbo.reviews TO [funding-api];
GRANT SELECT, INSERT ON dbo.changes TO [funding-api];

-- Add the approved Entra reporting group separately:
-- CREATE USER [Funding readers] FROM EXTERNAL PROVIDER;
-- ALTER ROLE funding_reader ADD MEMBER [Funding readers];
