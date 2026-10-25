"""Environment/approval guards must reject a wrong target before opening a connection."""
from dataclasses import replace
from unittest.mock import Mock
import pytest

from app.test_data.database import (CleanDatabaseError, ConnectionConfig, create_database, migrate,
                                    load_dataset, require_confirmation)
from app.test_data.generator import generate
from app.test_data.models import GenerationConfig

CONFIG = ConnectionConfig("inventory_ai_clean", "synthetic_user", "SYNTHETIC_SECRET", "localhost", 5432)


@pytest.mark.parametrize("name", ["inventory", "postgres", "inventory_ai_clean ", "INVENTORY_AI_CLEAN"])
def test_wrong_config_never_connects(name):
    connection = Mock()
    with pytest.raises(CleanDatabaseError):
        load_dataset(replace(CONFIG, name=name), generate(), GenerationConfig(), apply=True,
                     confirm_db="inventory_ai_clean", connection_factory=connection)
    connection.assert_not_called()


@pytest.mark.parametrize("confirmation", [None, "inventory", "yes", "force"])
def test_apply_requires_exact_database_confirmation(confirmation):
    with pytest.raises(CleanDatabaseError):
        require_confirmation(True, confirmation)


def test_environment_conflicts_are_not_silently_overridden_or_printed(tmp_path, monkeypatch):
    path = tmp_path / ".env.clean.local"
    path.write_text("DB_NAME=inventory_ai_clean\nDB_HOST=localhost\nDB_PORT=5432\nDB_USER=reader\nDB_PASSWORD=FAKE_FILE_SECRET\n", encoding="utf-8")
    for key in ("DB_NAME", "DB_HOST", "DB_PORT", "DB_USER", "DB_PASSWORD"):
        monkeypatch.delenv(key, raising=False)
    assert ConnectionConfig.from_env(path).name == "inventory_ai_clean"
    monkeypatch.setenv("DB_NAME", "inventory")
    with pytest.raises(CleanDatabaseError, match="DB_NAME"):
        ConnectionConfig.from_env(path)
    monkeypatch.setenv("DB_NAME", "inventory_ai_clean")
    monkeypatch.setenv("DB_PASSWORD", "FAKE_SHELL_SECRET")
    with pytest.raises(CleanDatabaseError) as captured:
        ConnectionConfig.from_env(path)
    assert "SECRET" not in str(captured.value)


def test_cli_errors_hide_driver_credentials(tmp_path, monkeypatch, capsys):
    from app.test_data import cli
    monkeypatch.setattr(ConnectionConfig, "from_env", lambda path: CONFIG)
    monkeypatch.setattr(cli, "create_database", Mock(side_effect=RuntimeError("password=SECRET")))
    assert cli.main("prepare", ["create", "--report", str(tmp_path / "report.json")]) == 1
    assert "SECRET" not in capsys.readouterr().out
    assert "SECRET" not in (tmp_path / "report.json").read_text(encoding="utf-8")
