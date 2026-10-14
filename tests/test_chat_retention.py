"""Retention command and physical chat-history purge checks."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from src.chat_repository import ChatCitationRow, ChatMessageRow, ChatRow
from src.chat_retention import (
    PurgeResult,
    RetentionSettings,
    SqlChatRetentionRepository,
    main,
    purge_due_data,
)
from src.document_repository import Base
from src.domain import ConfigurationError
from src.profile_repository import RoleRow, UserRow

NOW = datetime(2026, 10, 14, tzinfo=timezone.utc)


@pytest.fixture
def retention_database(tmp_path: Path) -> Engine:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'retention.db'}")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection: object, _record: object) -> None:
        cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    old = NOW - timedelta(days=30)
    recent = NOW - timedelta(days=28)
    with Session(engine) as session, session.begin():
        session.add(RoleRow(id=1, name="owner"))
        session.flush()
        session.add_all(
            [
                _user(1),
                _user(2, deleted_at=old),
                _user(3, deleted_at=recent),
            ]
        )
        session.flush()
        session.add_all(
            [
                _chat(10, 1),
                _chat(11, 1, deleted_at=old),
                _chat(12, 1, deleted_at=recent),
                _chat(13, 2),
                _chat(14, 3),
            ]
        )
        session.flush()
        message_ids = [chat_id + 90 for chat_id in range(10, 15)]
        session.add_all(
            [
                ChatMessageRow(
                    id=message_id,
                    chat_id=message_id - 90,
                    speaker="assistant",
                    content="Answer",
                    created_at=NOW,
                )
                for message_id in message_ids
            ]
        )
        session.flush()
        for message_id in message_ids:
            session.add(
                ChatCitationRow(
                    id=message_id,
                    message_id=message_id,
                    citation_number=1,
                    document_id="policy",
                    index_version=1,
                    chunk_index=0,
                    display_name="policy.pdf",
                    source_uri="s3://private/policy.pdf",
                )
            )
    return engine


def test_purge_removes_due_chat_and_deleted_user_content(
    retention_database: Engine,
) -> None:
    repository = SqlChatRetentionRepository(
        retention_database.url, engine=retention_database
    )

    result = repository.purge_batch(NOW - timedelta(days=29), batch_size=100)

    assert result == PurgeResult(users=1, chats=1)
    with Session(retention_database) as session:
        assert session.scalars(select(UserRow.id).order_by(UserRow.id)).all() == [1, 3]
        assert session.scalars(select(ChatRow.id).order_by(ChatRow.id)).all() == [
            10,
            12,
            14,
        ]
        assert session.scalars(
            select(ChatMessageRow.chat_id).order_by(ChatMessageRow.chat_id)
        ).all() == [10, 12, 14]
        assert session.scalars(
            select(ChatCitationRow.message_id).order_by(ChatCitationRow.message_id)
        ).all() == [100, 102, 104]

    assert repository.purge_batch(
        NOW - timedelta(days=29), batch_size=100
    ).empty


def test_purge_processes_all_rows_across_bounded_batches(
    retention_database: Engine,
) -> None:
    repository = SqlChatRetentionRepository(
        retention_database.url, engine=retention_database
    )

    result = purge_due_data(
        repository,
        RetentionSettings(min_age_days=29, batch_size=1),
        now=NOW,
    )

    assert result == PurgeResult(users=1, chats=1)


@pytest.mark.parametrize(
    ("name", "value"),
    [("CHAT_PURGE_MIN_AGE_DAYS", "30"), ("CHAT_PURGE_BATCH_SIZE", "0")],
)
def test_retention_settings_reject_values_that_break_bounds(
    monkeypatch: pytest.MonkeyPatch, name: str, value: str
) -> None:
    monkeypatch.setenv(name, value)

    with pytest.raises(ConfigurationError):
        RetentionSettings.from_env()


def test_command_reports_failure_and_later_run_can_retry(
    capsys: pytest.CaptureFixture[str],
) -> None:
    failed = _FakeRepository(error=SQLAlchemyError("private database detail"))
    retried = _FakeRepository(results=[PurgeResult(users=1, chats=2), PurgeResult()])

    with (
        patch("src.chat_retention.RetentionSettings.from_env", return_value=RetentionSettings()),
        patch("src.chat_retention.database_url_from_env"),
        patch(
            "src.chat_retention.SqlChatRetentionRepository",
            side_effect=[failed, retried],
        ),
    ):
        assert main() == 1
        assert main() == 0

    captured = capsys.readouterr()
    failure = json.loads(captured.err.splitlines()[0])
    success = json.loads(captured.out.splitlines()[0])
    assert failure == {
        "error": "database operation failed",
        "event": "chat_retention_purge_failed",
    }
    assert "private database detail" not in captured.err
    assert success == {
        "event": "chat_retention_purge_completed",
        "purged_chats": 2,
        "purged_users": 1,
    }
    assert failed.closed
    assert retried.closed


class _FakeRepository:
    def __init__(
        self,
        *,
        error: SQLAlchemyError | None = None,
        results: list[PurgeResult] | None = None,
    ) -> None:
        self.error = error
        self.results = results or []
        self.closed = False

    def purge_batch(self, _cutoff: datetime, _batch_size: int) -> PurgeResult:
        if self.error is not None:
            raise self.error
        return self.results.pop(0)

    def close(self) -> None:
        self.closed = True


def _user(user_id: int, *, deleted_at: datetime | None = None) -> UserRow:
    return UserRow(
        id=user_id,
        email=f"user{user_id}@example.com",
        role_id=1,
        created_at=NOW,
        updated_at=NOW,
        deleted_at=deleted_at,
    )


def _chat(chat_id: int, user_id: int, *, deleted_at: datetime | None = None) -> ChatRow:
    return ChatRow(
        id=chat_id,
        user_id=user_id,
        title=f"Chat {chat_id}",
        status="active",
        created_at=NOW,
        updated_at=NOW,
        deleted_at=deleted_at,
    )
