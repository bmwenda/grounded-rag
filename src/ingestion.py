from collections.abc import Iterable
from pathlib import Path
from typing import Protocol

from langchain_core.documents import Document

from .config import Settings
from .document_registry import DocumentRegistry
from .domain import DocumentRecord, DocumentStatus, IngestionResult
from .embedding import vector_store
from .loader import load_and_chunk_file
from .storage import DocumentStorage, LocalDocumentStorage, PreparedSource


class DocumentVectorStore(Protocol):
    def add_documents(
        self, documents: list[Document], **kwargs: object
    ) -> list[str]: ...

    def delete(self, ids: list[str]) -> None: ...


class DocumentRegistryPort(Protocol):
    def register_source(
        self,
        source_path: Path,
        *,
        source_reference: str | None = None,
        display_name: str | None = None,
        content_type: str | None = None,
    ) -> DocumentRecord: ...

    def mark_processing(self, document_id: str) -> DocumentRecord: ...

    def mark_retry(self, document_id: str) -> DocumentRecord: ...

    def mark_ready(
        self, document_id: str, *, index_version: int, chunk_count: int
    ) -> DocumentRecord: ...

    def mark_failed(self, document_id: str, error: Exception) -> DocumentRecord: ...


class DocumentIngestionService:
    def __init__(
        self,
        settings: Settings,
        registry: DocumentRegistryPort,
        store: DocumentVectorStore,
        storage: DocumentStorage,
    ) -> None:
        self._settings = settings
        self._registry = registry
        self._store = store
        self._storage = storage

    def ingest_source(self, source_reference: str) -> IngestionResult:
        with self._storage.prepare_source(source_reference) as source:
            return self._ingest_prepared_source(source)

    def _ingest_prepared_source(self, source: PreparedSource) -> IngestionResult:
        record = self._registry.register_source(
            source.path,
            source_reference=source.source_reference,
            display_name=source.display_name,
            content_type=source.content_type,
        )
        if record.status is DocumentStatus.READY:
            return IngestionResult(document=record, indexed=False)

        target_version = record.index_version + 1
        try:
            chunks, chunk_ids = load_and_chunk_file(
                str(source.path),
                document_id=record.document_id,
                index_version=target_version,
                source_uri=record.source_path,
                display_name=record.display_name,
                chunk_size=self._settings.chunk_size,
                chunk_overlap=self._settings.chunk_overlap,
            )
        except Exception as error:  # noqa: BLE001 - loaders expose varied errors.
            return IngestionResult(
                document=self._registry.mark_failed(record.document_id, error),
                indexed=False,
            )

        old_chunk_ids = _chunk_ids(
            record.document_id,
            record.index_version,
            record.chunk_count,
        )
        for attempt in range(self._settings.ingestion_max_attempts):
            self._registry.mark_processing(record.document_id)
            written_ids: list[str] = []
            try:
                for batch in _batches(chunks, self._settings.embedding_batch_size):
                    batch_ids = chunk_ids[
                        len(written_ids) : len(written_ids) + len(batch)
                    ]
                    written_ids.extend(batch_ids)
                    self._store.add_documents(batch, ids=batch_ids)

                if old_chunk_ids:
                    self._store.delete(ids=old_chunk_ids)
                return IngestionResult(
                    document=self._registry.mark_ready(
                        record.document_id,
                        index_version=target_version,
                        chunk_count=len(chunk_ids),
                    ),
                    indexed=True,
                )
            except Exception as error:  # noqa: BLE001 - vector backends expose varied errors.
                _delete_quietly(self._store, written_ids)
                if attempt + 1 < self._settings.ingestion_max_attempts:
                    self._registry.mark_retry(record.document_id)
                    continue
                return IngestionResult(
                    document=self._registry.mark_failed(record.document_id, error),
                    indexed=False,
                )

        raise AssertionError("Ingestion attempts must not be empty")

    def ingest_sources(
        self, sources_dir: str | Path | None = None
    ) -> list[IngestionResult]:
        directory = (
            Path(sources_dir)
            if sources_dir is not None
            else self._settings.sources_directory
        )
        source_paths = sorted(
            source_path
            for source_path in directory.iterdir()
            if source_path.is_file()
        )
        return [self.ingest_source(str(source_path)) for source_path in source_paths]


def create_ingestion_service(
    settings: Settings,
    storage: DocumentStorage | None = None,
) -> DocumentIngestionService:
    return DocumentIngestionService(
        settings=settings,
        registry=DocumentRegistry(settings.database_url),
        store=vector_store(settings),
        storage=storage or LocalDocumentStorage(),
    )


def _batches(
    documents: list[Document],
    batch_size: int,
) -> Iterable[list[Document]]:
    for start in range(0, len(documents), batch_size):
        yield documents[start : start + batch_size]


def _chunk_ids(document_id: str, index_version: int, count: int) -> list[str]:
    if index_version == 0:
        return []
    return [f"{document_id}:{index_version}:{index}" for index in range(count)]


def _delete_quietly(store: DocumentVectorStore, chunk_ids: list[str]) -> None:
    if not chunk_ids:
        return
    try:
        store.delete(ids=chunk_ids)
    except Exception:  # noqa: BLE001, S110 - preserve the original ingestion error.
        pass
