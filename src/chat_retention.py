"""Scheduled physical deletion of soft-deleted chat data."""

import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, TextIO, cast

from dotenv import load_dotenv
from sqlalchemy import delete, select, text
from sqlalchemy.engine import URL, CursorResult, Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from .chat_repository import ChatRow
from .config import database_url_from_env
from .database import create_database_engine
from .domain import ConfigurationError
from .profile_repository import UserRow

DEFAULT_MIN_AGE_DAYS = 29
DEFAULT_BATCH_SIZE = 500
MAX_MIN_AGE_DAYS = 29
MAX_BATCH_SIZE = 10_000


@dataclass(frozen=True)
class RetentionSettings:
    min_age_days: int = DEFAULT_MIN_AGE_DAYS
    batch_size: int = DEFAULT_BATCH_SIZE

    @classmethod
    def from_env(cls) -> "RetentionSettings":
        load_dotenv()
        settings = cls(
            min_age_days=_integer_env(
                "CHAT_PURGE_MIN_AGE_DAYS", DEFAULT_MIN_AGE_DAYS
            ),
            batch_size=_integer_env("CHAT_PURGE_BATCH_SIZE", DEFAULT_BATCH_SIZE),
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        if not 1 <= self.min_age_days <= MAX_MIN_AGE_DAYS:
            raise ConfigurationError(
                f"CHAT_PURGE_MIN_AGE_DAYS must be between 1 and {MAX_MIN_AGE_DAYS}"
            )
        if not 1 <= self.batch_size <= MAX_BATCH_SIZE:
            raise ConfigurationError(
                f"CHAT_PURGE_BATCH_SIZE must be between 1 and {MAX_BATCH_SIZE}"
            )


@dataclass(frozen=True)
class PurgeResult:
    users: int = 0
    chats: int = 0

    def __add__(self, other: "PurgeResult") -> "PurgeResult":
        return PurgeResult(users=self.users + other.users, chats=self.chats + other.chats)

    @property
    def empty(self) -> bool:
        return self.users == 0 and self.chats == 0


class SqlChatRetentionRepository:
    def __init__(self, database_url: URL, *, engine: Engine | None = None) -> None:
        owned_engine = engine is None
        engine = engine or create_database_engine(database_url)
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
                connection.execute(select(UserRow).limit(0))
                connection.execute(select(ChatRow).limit(0))
        except (SQLAlchemyError, OSError, ImportError):
            if owned_engine:
                engine.dispose()
            raise ConfigurationError(
                "Chat retention database is unavailable or schema is incompatible"
            ) from None
        self._engine = engine
        self._sessions = sessionmaker(engine, expire_on_commit=False)

    def close(self) -> None:
        self._engine.dispose()

    def purge_batch(self, cutoff: datetime, batch_size: int) -> PurgeResult:
        """Delete one bounded batch; database cascades remove messages and citations."""
        due_chat_ids = (
            select(ChatRow.id)
            .where(ChatRow.deleted_at.is_not(None), ChatRow.deleted_at <= cutoff)
            .order_by(ChatRow.deleted_at, ChatRow.id)
            .limit(batch_size)
        )
        due_user_ids = (
            select(UserRow.id)
            .where(UserRow.deleted_at.is_not(None), UserRow.deleted_at <= cutoff)
            .order_by(UserRow.deleted_at, UserRow.id)
            .limit(batch_size)
        )
        with self._sessions.begin() as session:
            chat_result = cast(
                CursorResult[Any],
                session.execute(
                    delete(ChatRow)
                    .where(ChatRow.id.in_(due_chat_ids))
                    .execution_options(synchronize_session=False)
                ),
            )
            user_result = cast(
                CursorResult[Any],
                session.execute(
                    delete(UserRow)
                    .where(UserRow.id.in_(due_user_ids))
                    .execution_options(synchronize_session=False)
                ),
            )
            chats = chat_result.rowcount
            users = user_result.rowcount
        return PurgeResult(users=users, chats=chats)


def purge_due_data(
    repository: SqlChatRetentionRepository,
    settings: RetentionSettings,
    *,
    now: datetime | None = None,
) -> PurgeResult:
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(
        days=settings.min_age_days
    )
    total = PurgeResult()
    while True:
        batch = repository.purge_batch(cutoff, settings.batch_size)
        total += batch
        if batch.empty:
            return total


def main() -> int:
    repository: SqlChatRetentionRepository | None = None
    try:
        settings = RetentionSettings.from_env()
        repository = SqlChatRetentionRepository(database_url_from_env())
        result = purge_due_data(repository, settings)
    except ConfigurationError as error:
        _write_event("chat_retention_purge_failed", error=str(error), stream=sys.stderr)
        return 1
    except SQLAlchemyError:
        _write_event(
            "chat_retention_purge_failed",
            error="database operation failed",
            stream=sys.stderr,
        )
        return 1
    finally:
        if repository is not None:
            repository.close()

    _write_event(
        "chat_retention_purge_completed",
        purged_users=result.users,
        purged_chats=result.chats,
    )
    return 0


def _integer_env(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        return int(raw_value)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be an integer") from exc


def _write_event(
    event: str, *, stream: TextIO | None = None, **fields: object
) -> None:
    print(
        json.dumps({"event": event, **fields}, sort_keys=True),
        file=stream or sys.stdout,
    )


if __name__ == "__main__":
    raise SystemExit(main())
