"""PostgreSQL storage for the first authenticated profile."""

from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    select,
    text,
)
from sqlalchemy.engine import URL, Engine
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Mapped, Session, mapped_column, relationship, sessionmaker

from .database import create_database_engine
from .document_repository import Base
from .domain import ConfigurationError
from .profile import (
    DuplicateEmailError,
    Profile,
    ProfileNotFoundError,
    normalize_changes,
    normalize_email,
)


class RoleRow(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)


class UserRow(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("email = lower(email)", name="ck_users_email_normalized"),
        Index("ix_users_deleted_at", "deleted_at"),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    first_name: Mapped[str | None] = mapped_column(String)
    last_name: Mapped[str | None] = mapped_column(String)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), nullable=False)
    role: Mapped[RoleRow] = relationship()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SqlProfileRepository:
    def __init__(self, database_url: URL) -> None:
        engine: Engine | None = None
        try:
            engine = create_database_engine(database_url)
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
                connection.execute(select(RoleRow).limit(0))
                connection.execute(select(UserRow).limit(0))
        except (SQLAlchemyError, OSError, ImportError):
            if engine is not None:
                engine.dispose()
            raise ConfigurationError(
                "Profile database is unavailable or schema is incompatible"
            ) from None
        assert engine is not None
        self._engine = engine
        self._sessions = sessionmaker(engine, expire_on_commit=False)

    def close(self) -> None:
        self._engine.dispose()

    def get_owner(self) -> Profile | None:
        with self._sessions() as session:
            row = session.scalar(
                select(UserRow)
                .join(RoleRow)
                .where(RoleRow.name == "owner", UserRow.deleted_at.is_(None))
            )
            return _to_profile(row) if row is not None else None

    def update_profile(self, user_id: int, changes: dict[str, str | None]) -> Profile:
        normalized = normalize_changes(changes)
        try:
            with self._sessions.begin() as session:
                row = _active_user(session, user_id)
                if "email" in normalized:
                    email = normalized["email"]
                    assert email is not None
                    row.email = email
                if "first_name" in normalized:
                    row.first_name = normalized["first_name"]
                if "last_name" in normalized:
                    row.last_name = normalized["last_name"]
                row.updated_at = _timestamp()
                session.flush()
                return _to_profile(row)
        except IntegrityError:
            raise DuplicateEmailError from None

    def delete_profile(self, user_id: int) -> None:
        with self._sessions.begin() as session:
            row = _active_user(session, user_id)
            now = _timestamp()
            row.deleted_at = now
            row.updated_at = now

    def provision_owner(self, email: str) -> Profile:
        normalized_email = normalize_email(email)
        try:
            with self._sessions.begin() as session:
                role = session.scalar(
                    select(RoleRow).where(RoleRow.name == "owner").with_for_update()
                )
                if role is None:
                    raise ConfigurationError("Owner role is missing; apply migrations")
                existing = session.scalar(
                    select(UserRow).where(UserRow.role_id == role.id)
                )
                if existing is not None:
                    raise DuplicateEmailError("An owner has already been provisioned")
                now = _timestamp()
                row = UserRow(
                    email=normalized_email,
                    first_name=None,
                    last_name=None,
                    role=role,
                    created_at=now,
                    updated_at=now,
                    deleted_at=None,
                )
                session.add(row)
                session.flush()
                return _to_profile(row)
        except IntegrityError:
            raise DuplicateEmailError from None


def _active_user(session: Session, user_id: int) -> UserRow:
    row = session.scalar(
        select(UserRow)
        .where(UserRow.id == user_id, UserRow.deleted_at.is_(None))
        .with_for_update()
    )
    if row is None:
        raise ProfileNotFoundError
    return row


def _timestamp() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _to_profile(row: UserRow) -> Profile:
    return Profile(
        id=row.id,
        email=row.email,
        first_name=row.first_name,
        last_name=row.last_name,
        role=row.role.name,
        created_at=_as_utc(row.created_at),
        updated_at=_as_utc(row.updated_at),
    )
