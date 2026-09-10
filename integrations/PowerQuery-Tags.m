let
    Source = Sql.Database("REPLACE.database.windows.net", "funding", [CreateNavigationProperties=false]),
    Tags = Source{[Schema="dbo", Item="v_funding_tags"]}[Data]
in
    Tags
