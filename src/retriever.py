import os
from typing import Any, Protocol, cast

from langchain_core.documents import Document

from .config import Settings
from .domain import RetrievalError, RetrievedChunk
from .embedding import vector_store

DEFAULT_RETRIEVAL_COUNT = 4
DEFAULT_RELEVANCE_THRESHOLD = 0.2


class SimilaritySearcher(Protocol):
    def similarity_search_with_relevance_scores(
        self,
        query: str,
        k: int = 4,
        **kwargs: Any,
    ) -> list[tuple[Document, float]]: ...


def get_searcher(settings: Settings | None = None) -> SimilaritySearcher:
    configured_settings = settings or Settings.from_env()
    return cast(SimilaritySearcher, vector_store(configured_settings))


def retrieve_documents(
    query: str,
    searcher: SimilaritySearcher | None = None,
    settings: Settings | None = None,
) -> list[RetrievedChunk]:
    """Return relevant chunks with stable request-local citation identifiers."""
    retrieval_count = settings.retrieval_count if settings else DEFAULT_RETRIEVAL_COUNT
    threshold = (
        settings.retrieval_relevance_threshold
        if settings
        else DEFAULT_RELEVANCE_THRESHOLD
    )
    searcher = searcher or get_searcher(settings)

    try:
        results = searcher.similarity_search_with_relevance_scores(
            query,
            k=retrieval_count,
        )
    except Exception as exc:
        raise RetrievalError("Document retrieval failed") from exc

    relevant_results = [
        (document, float(score)) for document, score in results if score >= threshold
    ]

    return [
        _to_retrieved_chunk(document, score, citation_id)
        for citation_id, (document, score) in enumerate(relevant_results, start=1)
    ]


def _to_retrieved_chunk(
    document: Document,
    score: float,
    citation_id: int,
) -> RetrievedChunk:
    metadata = document.metadata
    source = str(metadata.get("source", "unknown"))
    display_name = str(metadata.get("display_name") or os.path.basename(source))
    page_number = metadata.get("page_number")
    chunk_index = metadata.get("chunk_index", 0)
    index_version = metadata.get("index_version", 0)

    return RetrievedChunk(
        citation_id=citation_id,
        document_id=str(metadata.get("document_id") or source),
        display_name=display_name,
        page_number=page_number if isinstance(page_number, int) else None,
        chunk_index=chunk_index if isinstance(chunk_index, int) else 0,
        text=document.page_content,
        relevance_score=score,
        index_version=index_version if isinstance(index_version, int) else 0,
        source_uri=source,
    )
