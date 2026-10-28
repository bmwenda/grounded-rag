"""Check the running local web and pgvector stack without OpenAI calls."""

import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from langchain_core.embeddings import Embeddings
from sqlalchemy import delete

from src.config import Settings, database_url_from_env
from src.database import check_database_health, create_database_engine
from src.document_registry import DocumentRegistry
from src.document_repository import DocumentRow
from src.ingestion import DocumentIngestionService
from src.profile_repository import SqlProfileRepository
from src.retriever import retrieve_documents
from src.storage import LocalDocumentStorage
from src.vector_store import EMBEDDING_DIMENSIONS, PgVectorStore


class SmokeEmbeddings(Embeddings):
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_query(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return [1.0] + [0.0] * (EMBEDDING_DIMENSIONS - 1)


def main() -> None:
    database_url = database_url_from_env()
    check_database_health(database_url)
    owner_repository = SqlProfileRepository(database_url)
    try:
        owner = owner_repository.get_owner()
    finally:
        owner_repository.close()
    if owner is None:
        raise RuntimeError("Provision an owner before running the smoke check")

    base_url = os.getenv("LOCAL_WEB_URL", "http://127.0.0.1:8000")
    with urlopen(f"{base_url}/", timeout=5) as response:
        assert response.status == 200
        assert b"app-shell" in response.read()
    try:
        urlopen(f"{base_url}/v1/users/me", timeout=5)
    except HTTPError as error:
        assert error.code == 401
    else:
        raise AssertionError("Unauthenticated profile request must fail")

    token = os.environ["API_BEARER_TOKEN"]
    request = Request(
        f"{base_url}/v1/users/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    with urlopen(request, timeout=5) as response:
        assert response.status == 200
        assert json.load(response)["email"] == owner.email

    settings = Settings(
        openai_api_key="smoke-test-only",
        openai_model="smoke-test-only",
        database_url=database_url,
    )
    store = PgVectorStore(database_url, SmokeEmbeddings())
    registry = DocumentRegistry(database_url)
    engine = create_database_engine(database_url)
    document_id: str | None = None
    try:
        with TemporaryDirectory(prefix="simple-rag-smoke-") as directory:
            source = Path(directory) / "smoke.txt"
            source.write_text("The local Docker pgvector smoke check passes.")
            result = DocumentIngestionService(
                settings, registry, store, LocalDocumentStorage()
            ).ingest_source(str(source))
            document_id = result.document.document_id
            assert result.indexed, result.document.error_code
            matches = retrieve_documents(
                "Docker pgvector smoke check", searcher=store, settings=settings
            )
            assert any(chunk.document_id == document_id for chunk in matches)
    finally:
        if document_id is not None:
            with engine.begin() as connection:
                connection.execute(
                    delete(DocumentRow).where(DocumentRow.document_id == document_id)
                )
        engine.dispose()
    print("Local database, browser/API, authentication, ingestion, and retrieval passed.")


if __name__ == "__main__":
    main()
