from unittest.mock import patch

import pytest
from sqlalchemy.engine import URL

from src.config import Settings
from src.domain import ConfigurationError
from src.embedding import embeddings
from src.model import get_chat_model


def settings(provider: str) -> Settings:
    return Settings(
        llm_api_key="" if provider == "ollama" else "chat-key",
        llm_model="test-model",
        llm_provider=provider,
        llm_base_url="http://chat.example",
        embedding_api_key="embedding-key",
        database_url=URL.create("postgresql+psycopg", database="test"),
    )


@pytest.mark.parametrize(
    ("provider", "client", "model_parameter"),
    [
        ("openai", "ChatOpenAI", "model"),
        ("anthropic", "ChatAnthropic", "model_name"),
        ("ollama", "ChatOllama", "model"),
    ],
)
def test_native_provider_selection(
    provider: str, client: str, model_parameter: str
) -> None:
    with patch(f"src.model.{client}") as constructor:
        assert get_chat_model(settings(provider)) is constructor.return_value
        assert constructor.call_args.kwargs[model_parameter] == "test-model"
        assert constructor.call_args.kwargs["base_url"] == "http://chat.example"
        if provider != "ollama":
            assert (
                constructor.call_args.kwargs["api_key"].get_secret_value() == "chat-key"
            )
        else:
            assert "api_key" not in constructor.call_args.kwargs


@pytest.mark.parametrize("provider", ["anthropic", "ollama"])
def test_embeddings_do_not_inherit_native_chat_endpoint(provider: str) -> None:
    with patch("src.embedding.OpenAIEmbeddings") as constructor:
        embeddings(settings(provider))
        assert constructor.call_args.kwargs["base_url"] is None
        assert (
            constructor.call_args.kwargs["api_key"].get_secret_value()
            == "embedding-key"
        )


@pytest.mark.parametrize("provider", ["unknown", "anthropic", "ollama"])
def test_invalid_provider_or_missing_embedding_key(provider: str) -> None:
    from dataclasses import replace

    with pytest.raises(ConfigurationError):
        replace(settings(provider), embedding_api_key=None).validate()


def test_hosted_chat_requires_key() -> None:
    from dataclasses import replace

    with pytest.raises(ConfigurationError, match="LLM_API_KEY"):
        replace(settings("anthropic"), llm_api_key="").validate()


def test_ollama_environment_needs_only_embedding_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("src.config.load_dotenv", lambda: None)
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("LLM_MODEL", "llama3.2")
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setenv("EMBEDDING_API_KEY", "embedding-key")
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/test")
    configured = Settings.from_env()
    assert configured.llm_provider == "ollama"
    assert configured.llm_api_key == ""
