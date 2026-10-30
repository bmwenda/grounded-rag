
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


def test_generic_model_settings_override_legacy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("src.config.load_dotenv", lambda: None)
    monkeypatch.setenv("LLM_API_KEY", "provider-key")
    monkeypatch.setenv("LLM_MODEL", "provider-model")
    monkeypatch.setenv("OPENAI_API_KEY", "legacy-key")
    monkeypatch.setenv("OPENAI_MODEL", "legacy-model")
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/test")
    monkeypatch.setenv("LLM_BASE_URL", "https://chat.example/v1")
    monkeypatch.setenv("EMBEDDING_BASE_URL", "https://embed.example/v1")
    monkeypatch.setenv("EMBEDDING_API_KEY", "embedding-key")
    monkeypatch.setenv("EMBEDDING_MODEL", "embedding-model")
    settings = Settings.from_env()
    assert settings.openai_api_key == "provider-key"
    assert settings.openai_model == "provider-model"
    from unittest.mock import patch

    from src.embedding import embeddings
    from src.model import get_chat_model

    with patch("src.model.ChatOpenAI") as chat:
        get_chat_model(settings)
        assert chat.call_args.kwargs["base_url"] == "https://chat.example/v1"
        assert chat.call_args.kwargs["model"] == "provider-model"
    with patch("src.embedding.OpenAIEmbeddings") as embed:
        embeddings(settings)
        assert embed.call_args.kwargs["base_url"] == "https://embed.example/v1"
        assert embed.call_args.kwargs["model"] == "embedding-model"
        assert embed.call_args.kwargs["api_key"].get_secret_value() == "embedding-key"
