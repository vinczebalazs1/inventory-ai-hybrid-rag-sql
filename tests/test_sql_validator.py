import pytest
from app.security.sql_validator import validate_sql, SQLValidationError


def test_valid_select():
    # Az egyszerű, csak olvasó SELECT a várt sikeres út.
    sql = "SELECT name FROM inventory_items"
    assert validate_sql(sql) == sql


def test_reject_delete():
    # Módosító utasítás soha ne legyen futtatható generált SQL-ből.
    with pytest.raises(SQLValidationError):
        validate_sql("DELETE FROM inventory_items")


def test_reject_drop():
    # A több utasításból álló romboló terhelést el kell utasítani.
    with pytest.raises(SQLValidationError):
        validate_sql("SELECT * FROM inventory_items; DROP TABLE inventory_items;")


def test_reject_comments():
    # Az SQL kommenteket tiltjuk, mert terheléseket rejthetnek vagy elfedhetnek.
    with pytest.raises(SQLValidationError):
        validate_sql("SELECT * FROM inventory_items -- comment")
