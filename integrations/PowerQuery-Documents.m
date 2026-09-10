let
    Server = "REPLACE.database.windows.net",
    Database = "funding",
    Source = Sql.Database(Server, Database, [CreateNavigationProperties=false]),
    Documents = Source{[Schema="dbo", Item="v_funding_documents"]}[Data],
    Current = Table.SelectRows(Documents, each [active] = true),
    Selected = Table.SelectColumns(Current, {
        "opportunity_id", "document_id", "parent_document_id", "role", "depth", "is_root",
        "url", "title", "state", "extraction_status", "limitation", "error", "media_type",
        "byte_count", "page_count", "checked_at", "last_success_at", "current_sha256"
    })
in
    Selected
