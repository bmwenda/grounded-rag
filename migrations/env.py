from alembic import context

import src.chat_repository
import src.profile_repository
import src.vector_store  # noqa: F401 - register vector table in metadata
from src.config import database_url_from_env
from src.database import create_database_engine
from src.document_repository import Base

config = context.config
target_metadata = Base.metadata
database_url = database_url_from_env()


def run_migrations_offline() -> None:
    """Render migration SQL without connecting to the database."""
    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Apply migrations using the configured database URL."""
    engine = create_database_engine(database_url)
    try:
        with engine.connect() as connection:
            context.configure(connection=connection, target_metadata=target_metadata)
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
