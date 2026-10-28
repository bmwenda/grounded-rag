from typing import Any

import pytest
from langchain_core.documents import Document
from sqlalchemy.engine import URL

from src.config import Settings
from src.domain import RetrievalError
from src.retriever import retrieve_documents


class FakeSearcher:
    def __init__(
        self,
        results: list[tuple[Document, float]] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.results = results or []
        self.error = error
        self.query: str | None = None
        self.k: int | None = None

    def similarity_search_with_relevance_scores(
        self,
        query: str,
        k: int = 4,
        **kwargs: Any,
    ) -> list[tuple[Document, float]]:
        self.query = query
        self.k = k
        if self.error:
            raise self.error
        return self.results


def settings(*, threshold: float = 0.2, count: int = 4) -> Settings:
    return Settings(
        openai_api_key="test-key",
        openai_model="test-model",
        database_url=URL.create("postgresql+psycopg", database="test"),
        retrieval_count=count,
        retrieval_relevance_threshold=threshold,
    )


def document(
    content: str,
    *,
    source: str = "/documents/policies.pdf",
    page_number: int | None = 3,
    chunk_index: int = 0,
) -> Document:
    metadata: dict[str, str | int] = {
        "document_id": "policies_pdf",
        "display_name": "policies.pdf",
        "source": source,
        "chunk_index": chunk_index,
    }
    if page_number is not None:
        metadata["page_number"] = page_number
    return Document(page_content=content, metadata=metadata)


def test_retrieve_documents_returns_structured_scored_chunks() -> None:
    searcher = FakeSearcher([(document("Leave policy details"), 0.91)])

    chunks = retrieve_documents(
        "What is the leave policy?",
        searcher=searcher,
        settings=settings(count=6),
    )

    assert searcher.query == "What is the leave policy?"
    assert searcher.k == 6
    assert len(chunks) == 1
    assert chunks[0].citation_id == 1
    assert chunks[0].document_id == "policies_pdf"
    assert chunks[0].display_name == "policies.pdf"
    assert chunks[0].page_number == 3
    assert chunks[0].chunk_index == 0
    assert chunks[0].text == "Leave policy details"
    assert chunks[0].relevance_score == 0.91


def test_retrieve_documents_filters_below_threshold_and_renumbers() -> None:
    searcher = FakeSearcher(
        [
            (document("Irrelevant"), 0.3),
            (document("Relevant", page_number=4), 0.8),
        ]
    )

    chunks = retrieve_documents(
        "question",
        searcher=searcher,
        settings=settings(threshold=0.5),
    )

    assert [chunk.citation_id for chunk in chunks] == [1]
    assert [chunk.text for chunk in chunks] == ["Relevant"]


def test_retrieve_documents_returns_empty_when_no_result_passes_threshold() -> None:
    searcher = FakeSearcher([(document("Irrelevant"), 0.1)])

    assert (
        retrieve_documents(
            "question",
            searcher=searcher,
            settings=settings(threshold=0.5),
        )
        == []
    )


def test_retrieve_documents_wraps_failures() -> None:
    with pytest.raises(RetrievalError, match="Document retrieval failed"):
        retrieve_documents(
            "question",
            searcher=FakeSearcher(error=OSError()),
            settings=settings(),
        )
