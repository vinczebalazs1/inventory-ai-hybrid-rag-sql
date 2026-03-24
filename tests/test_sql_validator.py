import pytest
from app.security.sql_validator import validate_sql, SQLValidationError


def test_valid_select():
    sql = "SELECT name FROM inventory_items"
    assert validate_sql(sql) == sql


def test_reject_delete():
    with pytest.raises(SQLValidationError):
        validate_sql("DELETE FROM inventory_items")


def test_reject_drop():
    with pytest.raises(SQLValidationError):
        validate_sql("SELECT * FROM inventory_items; DROP TABLE inventory_items;")


def test_reject_comments():
    with pytest.raises(SQLValidationError):
        validate_sql("SELECT * FROM inventory_items -- comment")