from langchain_openai import OpenAIEmbeddings
from pydantic import SecretStr

from .config import Settings
from .vector_store import PgVectorStore


def embeddings(settings: Settings | None = None) -> OpenAIEmbeddings:
    settings = settings or Settings.from_env()
    return OpenAIEmbeddings(
        api_key=SecretStr(settings.embedding_api_key or settings.llm_api_key),
        base_url=settings.embedding_base_url or settings.llm_base_url,
        model=settings.embedding_model,
    )


def vector_store(settings: Settings | None = None) -> PgVectorStore:
    settings = settings or Settings.from_env()
    return PgVectorStore(settings.database_url, embeddings(settings))


def save_documents(settings: Settings | None = None) -> list[str]:
    """Ingest all local sources and return documents indexed in this run."""

    settings = settings or Settings.from_env()
    from .ingestion import create_ingestion_service

    results = create_ingestion_service(settings).ingest_sources()
    return [result.document.display_name for result in results if result.indexed]
