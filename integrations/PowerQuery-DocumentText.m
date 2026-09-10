// Full text is split into numbered parts: Excel/Power BI cell limits must not truncate conditions.
// Join document_id to PowerQuery-Documents and opportunity_id to the funding table.
let
    Server = "REPLACE.database.windows.net",
    Database = "funding",
    Source = Sql.Database(Server, Database, [CreateNavigationProperties=false]),
    Texts = Value.NativeQuery(Source,
        "SELECT d.id AS document_id, d.current_sha256 AS sha256, b.text AS full_text FROM dbo.documents d JOIN dbo.document_blobs b ON b.sha256=d.current_sha256 WHERE EXISTS (SELECT 1 FROM dbo.opportunity_documents od WHERE od.document_id=d.id AND od.active=1 AND od.limitation IS NULL)", null),
    Chunks = Table.AddColumn(Texts, "parts", each
        let parts = List.Split(Text.ToList([full_text]), 16000)
        in List.Transform(List.Positions(parts), (i) => [part_number=i+1, text=Text.Combine(parts{i})])),
    WithoutOriginal = Table.RemoveColumns(Chunks, {"full_text"}),
    ExpandList = Table.ExpandListColumn(WithoutOriginal, "parts"),
    ExpandParts = Table.ExpandRecordColumn(ExpandList, "parts", {"part_number", "text"}),
    Typed = Table.TransformColumnTypes(ExpandParts, {{"part_number", Int64.Type}, {"text", type text}})
in
    Typed
