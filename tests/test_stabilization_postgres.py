"""Ranking regressions on a disposable PostgreSQL cluster, never DB_* config."""
from test_matching_postgres import inventory, isolated_postgres  # noqa: F401


def test_live_primary_conflict_is_independent_of_candidate_limit(inventory):
    repo, columns, settings, execute = inventory
    execute('CREATE UNIQUE INDEX test_inventory_key ON inventory_items (inventory_number)')
    execute("INSERT INTO inventory_items (inventory_number,item_code,name,location) "
            "SELECT 'X-' || i, 'SHARED', 'Dell Latitude 5550', 'LIB' FROM generate_series(1,4000) AS i")
    execute("INSERT INTO inventory_items (inventory_number,item_code,name,location) VALUES ('TARGET','LAT5540','Dell Latitude 5540','KGK')")
    result = repo.search({'inventory_number':'TARGET','item_code':'SHARED','name':'Dell Latitude 5550'}, columns,
                        settings.model_copy(update={'max_candidates':1,'max_scan_rows':1}))
    assert len(result.records)==1 and result.records[0].values['inventory_number']=='TARGET'
    assert result.metadata.inventory_lookup.complete and result.metadata.scanned_rows==1
    assert not result.metadata.fuzzy_search.attempted


def test_live_secondary_query_ranks_support_before_limit(inventory):
    repo, columns, settings, execute = inventory
    execute('CREATE UNIQUE INDEX test_inventory_key ON inventory_items (inventory_number)')
    execute("INSERT INTO inventory_items (inventory_number,item_code,name,location) "
            "SELECT 'A-' || i, 'MODEL', 'Laptop 100', 'LIB' FROM generate_series(1,400) AS i")
    execute("INSERT INTO inventory_items (inventory_number,item_code,name,location) VALUES ('Z-LAST','MODEL','Laptop 100','NIK')")
    result=repo.search({'item_code':'MODEL','name':'Laptop 100','location':'NIK'},columns,
                      settings.model_copy(update={'max_candidates':1,'max_scan_rows':1}))
    assert result.records[0].values['inventory_number']=='Z-LAST'
    assert result.metadata.secondary_lookup.truncated and not result.metadata.complete
