// Name this query FundingPriorities. It produces one row per opportunity / group.
// Deploy config/priorities.json with the application; do not copy the rules here.
// File.Contents requires an accessible file and a gateway for scheduled cloud refresh.
// For SharePoint, replace ConfigBytes with your authenticated SharePoint file query.
let
    Server = "REPLACE.database.windows.net",
    Database = "funding",
    PriorityConfigPath = "C:\funding\config\priorities.json",
    ConfigBytes = File.Contents(PriorityConfigPath),
    Definitions = Json.Document(ConfigBytes),
    Allowed = {"source_id", "funder", "programme", "record_kind", "title_contains", "external_id_prefix"},
    MatchRule = (row as record, rule as record) as logical =>
        let
            Keys = Record.FieldNames(rule),
            Valid = List.Count(Keys) > 0 and List.AllTrue(List.Transform(Keys,
                (key) => List.Contains(Allowed, key) and List.Count(Record.Field(rule, key)) > 0)),
            Matches = if not Valid then error "Invalid funding priority rule" else
                List.AllTrue(List.Transform(Keys, (key) =>
                    let Values = Record.Field(rule, key) in
                    if key = "title_contains" then
                        List.AnyTrue(List.Transform(Values, (value) => Text.Contains(row[title], value, Comparer.OrdinalIgnoreCase)))
                    else if key = "external_id_prefix" then
                        List.AnyTrue(List.Transform(Values, (value) => Text.StartsWith(row[external_id], value, Comparer.Ordinal)))
                    else List.Contains(Values, Record.Field(row, key), Comparer.Ordinal)))
        in Matches,
    Source = Sql.Database(Server, Database, [CreateNavigationProperties=false]),
    Funding = Table.SelectColumns(Source{[Schema="dbo", Item="v_funding"]}[Data],
        {"id", "source_id", "external_id", "title", "funder", "programme", "record_kind"}),
    WithGroups = Table.AddColumn(Funding, "groups", (row) =>
        List.Transform(List.Select(Definitions, (definition) =>
            if List.Count(definition[rules]) = 0 then error "Empty funding priority definition"
            else List.AnyTrue(List.Transform(definition[rules], (rule) => MatchRule(row, rule)))),
            (definition) => [priority_id=Int64.From(definition[id]), priority_name=definition[name]]), type list),
    Matched = Table.SelectRows(WithGroups, each List.Count([groups]) > 0),
    OnlyKeys = Table.SelectColumns(Matched, {"id", "groups"}),
    ExpandedList = Table.ExpandListColumn(OnlyKeys, "groups"),
    ExpandedRecord = Table.ExpandRecordColumn(ExpandedList, "groups", {"priority_id", "priority_name"}),
    Renamed = Table.RenameColumns(ExpandedRecord, {{"id", "opportunity_id"}}),
    Typed = Table.TransformColumnTypes(Renamed, {{"opportunity_id", type text}, {"priority_id", Int64.Type}, {"priority_name", type text}})
in
    Typed
