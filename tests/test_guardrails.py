from app.security.guardrails import ensure_limit


def test_add_limit():
    # LIMIT nélküli lekérdezésnek meg kell kapnia az alapértelmezett biztonsági limitet.
    sql = "SELECT * FROM inventory_items"
    out = ensure_limit(sql)
    assert "LIMIT" in out.upper()


def test_keep_existing_limit():
    # A biztonságos explicit LIMIT-et nem szabad módosítani.
    sql = "SELECT * FROM inventory_items LIMIT 10"
    out = ensure_limit(sql)
    assert "LIMIT 10" in out.upper()
