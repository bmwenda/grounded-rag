from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.engine import URL

from src import db_cli
from src.domain import ConfigurationError

LOCAL_DATABASE_URL = URL.create(
    "postgresql+psycopg",
    username="developer",
    host="localhost",
    port=5432,
    database="grounded_rag_local",
)


def test_create_database_creates_missing_local_database() -> None:
    connection = MagicMock()
    connection.execute.return_value.fetchone.return_value = None

    with (
        patch("src.db_cli.database_url_from_env", return_value=LOCAL_DATABASE_URL),
        patch("src.db_cli.psycopg.connect") as connect,
    ):
        connect.return_value.__enter__.return_value = connection

        created = db_cli.create_database()

    assert created
    statements = [str(call.args[0]) for call in connection.execute.call_args_list]
    assert "SELECT 1 FROM pg_database WHERE datname = %s" in statements[0]
    assert "CREATE DATABASE" in statements[1]
    assert connection.execute.call_args_list[0].args[1] == ("grounded_rag_local",)
    assert connect.call_args.kwargs["autocommit"] is True


def test_create_database_skips_existing_database(capsys: pytest.CaptureFixture[str]) -> None:
    connection = MagicMock()
    connection.execute.return_value.fetchone.return_value = (1,)

    with (
        patch("src.db_cli.database_url_from_env", return_value=LOCAL_DATABASE_URL),
        patch("src.db_cli.psycopg.connect") as connect,
    ):
        connect.return_value.__enter__.return_value = connection

        created = db_cli.create_database()

    assert not created
    assert connection.execute.call_count == 1
    assert "already exists" in capsys.readouterr().out


def test_drop_database_requires_exact_confirmation() -> None:
    with (
        patch("src.db_cli.database_url_from_env", return_value=LOCAL_DATABASE_URL),
        patch("builtins.input", return_value="wrong-name"),
        patch("src.db_cli.psycopg.connect") as connect,
    ):
        dropped = db_cli.drop_database()

    assert not dropped
    connect.assert_not_called()


def test_drop_database_drops_after_confirmation() -> None:
    connection = MagicMock()
    connection.execute.return_value.fetchone.return_value = (1,)

    with (
        patch("src.db_cli.database_url_from_env", return_value=LOCAL_DATABASE_URL),
        patch("builtins.input", return_value="grounded_rag_local"),
        patch("src.db_cli.psycopg.connect") as connect,
    ):
        connect.return_value.__enter__.return_value = connection

        dropped = db_cli.drop_database()

    assert dropped
    assert "DROP DATABASE" in str(connection.execute.call_args.args[0])


def test_database_commands_reject_remote_urls() -> None:
    remote_url = LOCAL_DATABASE_URL.set(host="db.example.net")
    with (
        patch("src.db_cli.database_url_from_env", return_value=remote_url),
        pytest.raises(ConfigurationError, match="require a local PostgreSQL URL"),
        patch("src.db_cli.psycopg.connect") as connect,
    ):
        db_cli.create_database()

    connect.assert_not_called()


def test_migrate_command_rejects_remote_urls(capsys: pytest.CaptureFixture[str]) -> None:
    remote_url = LOCAL_DATABASE_URL.set(host="db.example.net")
    with patch("src.db_cli.database_url_from_env", return_value=remote_url):
        result = db_cli.main(["migrate"])

    assert result == 1
    assert "require a local PostgreSQL URL" in capsys.readouterr().out


def test_database_commands_reject_url_host_overrides() -> None:
    overridden_url = LOCAL_DATABASE_URL.update_query_dict({"hostaddr": "203.0.113.5"})
    with (
        patch("src.db_cli.database_url_from_env", return_value=overridden_url),
        pytest.raises(ConfigurationError, match="require a local PostgreSQL URL"),
    ):
        db_cli.create_database()


def test_database_commands_reject_postgres_system_database() -> None:
    system_url = LOCAL_DATABASE_URL.set(database="postgres")
    with (
        patch("src.db_cli.database_url_from_env", return_value=system_url),
        pytest.raises(ConfigurationError, match="system database"),
    ):
        db_cli.create_database()


def test_prepare_creates_database_and_applies_migrations() -> None:
    with (
        patch("src.db_cli.create_database") as create_database,
        patch("src.db_cli.upgrade_schema") as upgrade_schema,
    ):
        assert db_cli.main(["prepare"]) == 0

    create_database.assert_called_once_with()
    upgrade_schema.assert_called_once_with()
