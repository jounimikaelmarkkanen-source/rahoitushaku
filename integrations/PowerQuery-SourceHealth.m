let
    Source = Sql.Database("REPLACE.database.windows.net", "funding", [CreateNavigationProperties=false]),
    Health = Source{[Schema="dbo", Item="v_source_health"]}[Data]
in
    Health
