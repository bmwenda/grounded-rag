from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from .config import Settings


def get_chat_model(settings: Settings | None = None) -> ChatOpenAI:
    """Create the chat model used by the RAG answer-generation layer."""

    settings = settings or Settings.from_env()

    return ChatOpenAI(
        model=settings.llm_model,
        api_key=SecretStr(settings.llm_api_key),
        base_url=settings.llm_base_url,
        max_retries=2,
        timeout=30,
    )
