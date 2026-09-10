let
    Server = "REPLACE.database.windows.net",
    Database = "funding",
    Source = Sql.Database(Server, Database, [CreateNavigationProperties=false]),
    Funding = Source{[Schema="dbo", Item="v_funding"]}[Data],
    // Keep unknown geography: unknown does not mean ineligible.
    Candidates = Table.SelectRows(Funding, each
        ([record_kind] = "funding_scheme" or [effective_status] = "open" or [effective_status] = "rolling" or [effective_status] = "forthcoming" or [effective_status] = "unknown")
        and [eligibility] <> "ineligible"),
    Selected = Table.SelectColumns(Candidates, {
        "id", "source_id", "external_id", "title", "funder", "programme", "record_kind", "instrument", "effective_status",
        "opens_on", "deadline_on", "deadline_at", "deadline_model", "total_budget",
        "grant_max", "funding_rate", "currency", "geographic_scope", "eligibility",
        "city_role", "service_area", "needs_review", "source_name", "source_health",
        "canonical_url", "updated_at", "last_seen_at", "source_last_success_at",
        "content_state", "document_count", "fetched_count", "pending_document_count", "failed_document_count",
        "document_text_issues", "limited_document_count", "documents_checked_at"
    }),
    WithCascade = Table.AddColumn(Selected, "cascade", each
        [source_id] = "eu-funding" and Text.StartsWith([external_id], "cascade:"), type logical)
in
    WithCascade
