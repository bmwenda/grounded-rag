
import pytest
from sqlalchemy.engine import URL

from src.config import PROJECT_ROOT, Settings
from src.domain import ConfigurationError

TEST_DATABASE_URL = URL.create("postgresql+psycopg", database="test")


def test_settings_load_and_convert_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_MODEL", "test-model")
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql://app:secret@localhost:5432/simple_rag"
    )
    monkeypatch.setenv("RETRIEVAL_COUNT", "7")
    monkeypatch.setenv("RETRIEVAL_RELEVANCE_THRESHOLD", "0.65")
    monkeypatch.setenv("SOURCES_DIRECTORY", "local-documents")
    monkeypatch.setenv("S3_SOURCE_BUCKET", "source-bucket")
    monkeypatch.setenv("S3_SOURCE_PREFIX", "incoming")
    monkeypatch.setenv("MAX_DOCUMENT_SIZE_BYTES", "1234")

    settings = Settings.from_env()

    assert settings.openai_api_key == "test-key"
    assert settings.openai_model == "test-model"
    assert settings.database_url.drivername == "postgresql+psycopg"
    assert settings.database_url.database == "simple_rag"
    assert "secret" not in repr(settings)
    assert settings.retrieval_count == 7
    assert settings.retrieval_relevance_threshold == 0.65
    assert settings.sources_directory == PROJECT_ROOT / "local-documents"
    assert settings.s3_source_bucket == "source-bucket"
    assert settings.s3_source_prefix == "incoming"
    assert settings.max_document_size_bytes == 1234


def test_settings_reject_invalid_chunk_overlap() -> None:
    settings = Settings(
        openai_api_key="test-key",
        openai_model="test-model",
        database_url=TEST_DATABASE_URL,
        chunk_size=100,
        chunk_overlap=100,
    )

    with pytest.raises(ConfigurationError, match="smaller than CHUNK_SIZE"):
        settings.validate()


def test_settings_reject_invalid_relevance_threshold() -> None:
    settings = Settings(
        openai_api_key="test-key",
        openai_model="test-model",
        database_url=TEST_DATABASE_URL,
        retrieval_relevance_threshold=1.1,
    )

    with pytest.raises(ConfigurationError, match="must be between 0 and 1"):
        settings.validate()


def test_settings_reject_invalid_ingestion_configuration() -> None:
    settings = Settings(
        openai_api_key="test-key",
        openai_model="test-model",
        database_url=TEST_DATABASE_URL,
        embedding_batch_size=0,
    )

    with pytest.raises(ConfigurationError, match="EMBEDDING_BATCH_SIZE"):
        settings.validate()


def test_settings_reject_non_integer_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_MODEL", "test-model")
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/test")
    monkeypatch.setenv("RETRIEVAL_COUNT", "many")

    with pytest.raises(ConfigurationError, match="RETRIEVAL_COUNT must be an integer"):
        Settings.from_env()
