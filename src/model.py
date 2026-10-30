from langchain_anthropic import ChatAnthropic
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from .config import Settings


def get_chat_model(settings: Settings | None = None) -> BaseChatModel:
    """Create the selected native chat client."""
    settings = settings or Settings.from_env()
    settings.validate()
    if settings.llm_provider == "anthropic":
        return ChatAnthropic(
            model_name=settings.llm_model,
            stop=None,
            api_key=SecretStr(settings.llm_api_key),
            base_url=settings.llm_base_url,
            max_retries=2,
            timeout=30,
        )
    if settings.llm_provider == "ollama":
        return ChatOllama(
            model=settings.llm_model,
            base_url=settings.llm_base_url or "http://localhost:11434",
            client_kwargs={"timeout": 30},
        )
    return ChatOpenAI(
        model=settings.llm_model,
        api_key=SecretStr(settings.llm_api_key),
        base_url=settings.llm_base_url,
        max_retries=2,
        timeout=30,
    )
