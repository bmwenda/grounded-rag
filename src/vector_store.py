"""PostgreSQL pgvector storage shared by ingestion and retrieval."""

from collections.abc import Sequence
from typing import Any

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from pgvector.psycopg import register_vector
from pgvector.sqlalchemy import VECTOR
from sqlalchemy import (
    JSON,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    delete,
    event,
    select,
    text,
)
from sqlalchemy.engine import URL, Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Mapped, mapped_column, sessionmaker

from .database import create_database_engine
from .document_repository import Base
from .domain import ConfigurationError

EMBEDDING_DIMENSIONS = 3072


class DocumentChunkRow(Base):
    __tablename__ = "document_chunks"

    chunk_id: Mapped[str] = mapped_column(String, primary_key=True)
    document_id: Mapped[str] = mapped_column(
        String, ForeignKey("documents.document_id", ondelete="CASCADE"), nullable=False
    )
    index_version: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source_metadata: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(VECTOR(EMBEDDING_DIMENSIONS))


Index("ix_document_chunks_document_id", DocumentChunkRow.document_id)


class PgVectorStore:
    """Store versioned chunks and rank by cosine similarity."""

    def __init__(self, database_url: URL, embeddings: Embeddings) -> None:
        engine: Engine | None = None
        try:
            engine = create_database_engine(database_url)

            @event.listens_for(engine, "connect")
            def register_pgvector(connection: Any, _: object) -> None:
                register_vector(connection)

            with engine.connect() as connection:
                connection.execute(text("SELECT 1 FROM document_chunks LIMIT 0"))
        except (SQLAlchemyError, OSError, ImportError):
            if engine is not None:
                engine.dispose()
            raise ConfigurationError(
                "Vector database is unavailable or schema is incompatible"
            ) from None
        assert engine is not None
        self._sessions = sessionmaker(engine, expire_on_commit=False)
        self._embeddings = embeddings

    def add_documents(
        self, documents: list[Document], **kwargs: object
    ) -> list[str]:
        ids = kwargs.get("ids")
        if not isinstance(ids, list) or len(ids) != len(documents):
            raise ValueError("One chunk ID is required for each document")
        if not all(isinstance(chunk_id, str) for chunk_id in ids):
            raise ValueError("Chunk IDs must be strings")
        if not documents:
            return []

        vectors = self._embeddings.embed_documents(
            [document.page_content for document in documents]
        )
        if len(vectors) != len(documents) or any(
            len(vector) != EMBEDDING_DIMENSIONS for vector in vectors
        ):
            raise ValueError("Embedding dimensions do not match the vector schema")

        rows = []
        for chunk_id, document, vector in zip(ids, documents, vectors, strict=True):
            metadata = document.metadata
            document_id = metadata.get("document_id")
            index_version = metadata.get("index_version")
            chunk_index = metadata.get("chunk_index")
            if (
                not isinstance(document_id, str)
                or not isinstance(index_version, int)
                or not isinstance(chunk_index, int)
                or chunk_id != f"{document_id}:{index_version}:{chunk_index}"
            ):
                raise ValueError("Chunk metadata does not match its stable ID")
            rows.append(
                DocumentChunkRow(
                    chunk_id=chunk_id,
                    document_id=document_id,
                    index_version=index_version,
                    chunk_index=chunk_index,
                    content=document.page_content,
                    source_metadata=metadata,
                    embedding=vector,
                )
            )
        with self._sessions.begin() as session:
            for row in rows:
                session.merge(row)
        return ids

    def delete(self, ids: list[str]) -> None:
        if not ids:
            return
        with self._sessions.begin() as session:
            session.execute(delete(DocumentChunkRow).where(DocumentChunkRow.chunk_id.in_(ids)))

    def similarity_search_with_relevance_scores(
        self, query: str, k: int = 4, **kwargs: object
    ) -> list[tuple[Document, float]]:
        if k < 1:
            return []
        vector = self._embeddings.embed_query(query)
        if len(vector) != EMBEDDING_DIMENSIONS:
            raise ValueError("Embedding dimensions do not match the vector schema")
        distance = DocumentChunkRow.embedding.cosine_distance(vector)
        with self._sessions() as session:
            rows: Sequence[tuple[DocumentChunkRow, float]] = session.execute(
                select(DocumentChunkRow, distance)
                .order_by(distance, DocumentChunkRow.chunk_id)
                .limit(k)
            ).all()
        return [
            (
                Document(page_content=row.content, metadata=row.source_metadata),
                max(0.0, min(1.0, 1.0 - float(score))),
            )
            for row, score in rows
        ]
