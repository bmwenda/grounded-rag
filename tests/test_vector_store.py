"""pgvector integration checks against an isolated PostgreSQL database."""

import os
import subprocess
import sys
from datetime import datetime, timezone

import pytest
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from sqlalchemy import delete, insert
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError

import src.vector_store as vector_store_module
from src.config import Settings
from src.database import create_database_engine
from src.document_repository import DocumentRow
from src.domain import ConfigurationError
from src.retriever import retrieve_documents
from src.vector_store import EMBEDDING_DIMENSIONS, PgVectorStore


class FakeEmbeddings(Embeddings):
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_query(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        vector = [0.0] * EMBEDDING_DIMENSIONS
        vector[0 if "leave" in text else 1] = 1.0
        return vector


@pytest.mark.skipif(
    not os.getenv("PGVECTOR_TEST_DATABASE_URL"),
    reason="PGVECTOR_TEST_DATABASE_URL is required for the PostgreSQL integration test",
)
def test_pgvector_migration_ingestion_retrieval_replacement_and_deletion() -> None:
    raw_url = os.environ["PGVECTOR_TEST_DATABASE_URL"]
    migration_env = {**os.environ, "DATABASE_URL": raw_url}
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        env=migration_env,
        check=True,
        capture_output=True,
        text=True,
    )
    database_url = make_url(raw_url)
    engine = create_database_engine(database_url)
    now = datetime.now(timezone.utc)
    try:
        with engine.begin() as connection:
            connection.execute(
                insert(DocumentRow).values(
                    document_id="test-document",
                    source_path="s3://test-bucket/incoming/leave.txt",
                    display_name="leave.txt",
                    content_type="text/plain",
                    size_bytes=10,
                    checksum_sha256="a" * 64,
                    status="pending",
                    index_version=1,
                    chunk_count=1,
                    retry_count=0,
                    created_at=now,
                    updated_at=now,
                )
            )

        store = PgVectorStore(database_url, FakeEmbeddings())
        first = Document(
            page_content="leave policy",
            metadata={
                "document_id": "test-document",
                "index_version": 1,
                "chunk_index": 0,
                "source": "s3://test-bucket/incoming/leave.txt",
                "display_name": "leave.txt",
            },
        )
        assert store.add_documents([first], ids=["test-document:1:0"]) == [
            "test-document:1:0"
        ]
        results = store.similarity_search_with_relevance_scores("leave", k=2)
        assert len(results) == 1
        assert results[0][0].metadata == first.metadata
        assert results[0][1] == pytest.approx(1.0)

        replacement = Document(
            page_content="other policy",
            metadata={**first.metadata, "index_version": 2},
        )
        store.add_documents([replacement], ids=["test-document:2:0"])
        store.delete(ids=["test-document:1:0"])
        results = store.similarity_search_with_relevance_scores("leave", k=2)
        assert len(results) == 1
        assert results[0][0].metadata["index_version"] == 2
        assert results[0][1] == pytest.approx(0.0)
        assert retrieve_documents(
            "leave",
            searcher=store,
            settings=Settings(
                openai_api_key="test-key",
                openai_model="test-model",
                database_url=database_url,
                retrieval_relevance_threshold=0.2,
            ),
        ) == []

        store.delete(ids=["test-document:2:0"])
        assert store.similarity_search_with_relevance_scores("leave") == []
    finally:
        with engine.begin() as connection:
            connection.execute(
                delete(DocumentRow).where(
                    DocumentRow.document_id == "test-document"
                )
            )
        engine.dispose()


def test_pgvector_rejects_malformed_chunk_ids() -> None:
    store = object.__new__(PgVectorStore)
    store._embeddings = FakeEmbeddings()
    document = Document(page_content="leave", metadata={})

    with pytest.raises(ValueError, match="One chunk ID"):
        store.add_documents([document], ids=[])

    with pytest.raises(ValueError, match="stable ID"):
        store.add_documents([document], ids=["wrong:1:0"])


def test_pgvector_rejects_incompatible_embedding_dimensions() -> None:
    class WrongDimensions(FakeEmbeddings):
        def embed_query(self, text: str) -> list[float]:
            return [1.0, 0.0]

    store = object.__new__(PgVectorStore)
    store._embeddings = WrongDimensions()
    document = Document(page_content="leave", metadata={})

    with pytest.raises(ValueError, match="Embedding dimensions"):
        store.add_documents([document], ids=["test-document:1:0"])

    with pytest.raises(ValueError, match="Embedding dimensions"):
        store.similarity_search_with_relevance_scores("leave")


def test_pgvector_reports_unavailable_database_without_connection_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unavailable(_url: object) -> object:
        raise OperationalError("connect", {}, Exception("private host"))

    monkeypatch.setattr(vector_store_module, "create_database_engine", unavailable)

    with pytest.raises(ConfigurationError, match="Vector database is unavailable") as error:
        PgVectorStore(make_url("postgresql+psycopg://localhost/test"), FakeEmbeddings())
    assert "private host" not in str(error.value)
