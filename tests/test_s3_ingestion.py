from __future__ import annotations

from pathlib import Path

import pytest
from langchain_core.documents import Document
from sqlalchemy.engine import URL

from src.config import Settings
from src.domain import DocumentStatus
from src.ingestion import DocumentIngestionService
from src.s3_events import sqs_s3_object_created_events
from src.s3_ingestion_handler import S3IngestionHandler
from src.storage import S3DocumentStorage, s3_source_uri
from tests.fakes import FakeDocumentRegistry


class FakeVectorStore:
    def add_documents(self, documents: list[Document], **kwargs: object) -> list[str]:
        raw_ids = kwargs["ids"]
        assert isinstance(raw_ids, list)
        return [str(chunk_id) for chunk_id in raw_ids]

    def delete(self, ids: list[str]) -> None:
        pass


class FakeS3Client:
    def __init__(self, objects: dict[tuple[str, str], bytes]) -> None:
        self.objects = objects
        self.downloads: list[tuple[str, str]] = []
        self.downloaded_paths: list[Path] = []

    def head_object(self, **kwargs: object) -> dict[str, object]:
        bucket = str(kwargs["Bucket"])
        key = str(kwargs["Key"])
        body = self.objects[(bucket, key)]
        return {
            "ContentLength": len(body),
            "ContentType": "text/plain",
        }

    def download_fileobj(self, bucket: str, key: str, fileobj: object) -> None:
        self.downloads.append((bucket, key))
        assert hasattr(fileobj, "write")
        assert hasattr(fileobj, "name")
        self.downloaded_paths.append(Path(fileobj.name))  # type: ignore[union-attr]
        fileobj.write(self.objects[(bucket, key)])  # type: ignore[union-attr]


def make_s3_service(
    client: FakeS3Client,
    *,
    max_document_size_bytes: int = 1000,
) -> tuple[DocumentIngestionService, FakeDocumentRegistry, S3DocumentStorage]:
    settings = Settings(
        openai_api_key="test-key",
        openai_model="test-model",
        database_url=URL.create("postgresql+psycopg", database="test"),
        chunk_size=20,
        chunk_overlap=0,
        max_document_size_bytes=max_document_size_bytes,
    )
    registry = FakeDocumentRegistry()
    storage = S3DocumentStorage(
        bucket="source-bucket",
        prefix="incoming",
        max_document_size_bytes=max_document_size_bytes,
        client=client,
    )
    return (
        DocumentIngestionService(settings, registry, FakeVectorStore(), storage),
        registry,
        storage,
    )


def test_ingest_s3_object_uses_stable_s3_identity_and_removes_temp_file() -> None:
    client = FakeS3Client(
        {("source-bucket", "incoming/leave policy.txt"): b"annual leave details"}
    )
    service, registry, _storage = make_s3_service(client)

    source_reference = s3_source_uri("source-bucket", "incoming/leave policy.txt")
    first = service.ingest_source(source_reference)
    second = service.ingest_source(source_reference)

    assert first.indexed is True
    assert second.indexed is False
    assert first.document.document_id == second.document.document_id
    assert first.document.source_path == (
        "s3://source-bucket/incoming/leave%20policy.txt"
    )
    assert first.document.display_name == "leave policy.txt"
    assert first.document.content_type == "text/plain"
    assert first.document.size_bytes == len(b"annual leave details")
    assert registry.get(first.document.document_id).status is DocumentStatus.READY
    assert client.downloads == [
        ("source-bucket", "incoming/leave policy.txt"),
        ("source-bucket", "incoming/leave policy.txt"),
    ]
    assert all(not path.exists() for path in client.downloaded_paths)


def test_s3_storage_rejects_objects_outside_the_configured_source_scope() -> None:
    client = FakeS3Client({("source-bucket", "incoming/large.txt"): b"x" * 11})
    service, _, storage = make_s3_service(client, max_document_size_bytes=10)

    with pytest.raises(ValueError, match="MAX_DOCUMENT_SIZE_BYTES"):
        storage.get_object("source-bucket", "incoming/large.txt")
    with pytest.raises(ValueError, match="MAX_DOCUMENT_SIZE_BYTES"):
        service.ingest_source(s3_source_uri("source-bucket", "incoming/large.txt"))
    with pytest.raises(ValueError, match="outside S3_SOURCE_PREFIX"):
        storage.get_object("source-bucket", "other/document.txt")
    with pytest.raises(ValueError, match="source bucket"):
        storage.get_object("another-bucket", "incoming/document.txt")
    assert client.downloads == []


def test_s3_storage_allows_markdown_sources() -> None:
    client = FakeS3Client({("source-bucket", "incoming/handbook.md"): b"# Handbook"})
    _, _, storage = make_s3_service(client)

    source = storage.get_object("source-bucket", "incoming/handbook.md")

    assert source.content_type == "text/plain"


def test_s3_event_handler_accepts_sqs_wrapped_object_created_events() -> None:
    client = FakeS3Client(
        {("source-bucket", "incoming/handbook.txt"): b"handbook content"}
    )
    service, _, _storage = make_s3_service(client)
    handler = S3IngestionHandler(service)
    event: dict[str, object] = {
        "Records": [
            {
                "eventSource": "aws:sqs",
                "body": (
                    '{"Records":[{"eventName":"ObjectCreated:Put","s3":'
                    '{"bucket":{"name":"source-bucket"},"object":'
                    '{"key":"incoming%2Fhandbook.txt"}}}]}'
                ),
            }
        ]
    }

    results = handler.handle(event)
    assert len(results) == 1
    assert results[0]["status"] == "ready"
    assert results[0]["indexed"] is True
    assert isinstance(results[0]["document_id"], str)
    assert list(sqs_s3_object_created_events({"Records": []})) == []
