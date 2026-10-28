import json
from pathlib import Path

from langchain_core.documents import Document

from src import loader


def test_docling_nested_metadata_is_preserved_for_json_storage(
    monkeypatch,
) -> None:
    docling_metadata = {
        "schema_name": "docling_core.transforms.chunker.DocMeta",
        "doc_items": [{"self_ref": "#/texts/0", "prov": [{"page_no": 1}]}],
        "origin": {"filename": "policies.txt", "mimetype": "text/markdown"},
    }
    monkeypatch.setattr(
        loader,
        "_load_file",
        lambda path: [
            Document(
                page_content="Leave policy details",
                metadata={"dl_meta": docling_metadata, "page": 0},
            )
        ],
    )

    chunks, _ = loader.load_and_chunk_file(
        "policies.txt", document_id="policy", index_version=1
    )

    metadata = chunks[0].metadata
    json.dumps(metadata)
    assert json.loads(metadata["dl_meta"]) == docling_metadata
    assert metadata["document_id"] == "policy"
    assert metadata["source"] == "policies.txt"
    assert metadata["page_number"] == 1
    assert metadata["index_version"] == 1


def test_load_and_chunk_sources_preserves_loader_metadata(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = tmp_path / "handbook.pdf"
    source.touch()
    monkeypatch.setattr(
        loader,
        "_load_file",
        lambda path: [
            Document(
                page_content="Leave policy details",
                metadata={"page": 2, "producer": "test"},
            )
        ],
    )

    chunks, chunk_ids, source_files = loader.load_and_chunk_sources(
        str(tmp_path),
        chunk_size=100,
        chunk_overlap=10,
    )

    assert source_files == ["handbook.pdf"]
    assert chunk_ids == ["handbook_pdf:0:0"]
    assert chunks[0].metadata == {
        "page": 2,
        "producer": "test",
        "document_id": "handbook_pdf",
        "display_name": "handbook.pdf",
        "source": str(source),
        "index_version": 0,
        "chunk_index": 0,
        "page_number": 3,
    }


def test_load_and_chunk_sources_ignores_directories(tmp_path: Path) -> None:
    (tmp_path / "nested").mkdir()

    chunks, chunk_ids, source_files = loader.load_and_chunk_sources(str(tmp_path))

    assert chunks == []
    assert chunk_ids == []
    assert source_files == []


def test_load_file_uses_generic_loader_for_markdown(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = tmp_path / "handbook.md"
    source.write_text("# Handbook", encoding="utf-8")
    calls: list[str] = []

    class FakeLoader:
        def __init__(self, *, file_path: str) -> None:
            calls.append(file_path)

        def load(self) -> list[Document]:
            return [Document(page_content="Handbook", metadata={})]

    monkeypatch.setattr(loader, "DoclingLoader", FakeLoader)

    assert loader._load_file(str(source))[0].page_content == "Handbook"
    assert calls == [str(source)]


def test_load_file_preserves_structured_json_as_searchable_text(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = tmp_path / "org-chart.json"
    payload = {"company": "Aetheris", "teams": [{"name": "RAG"}]}
    source.write_text(json.dumps(payload), encoding="utf-8")

    class UnexpectedLoader:
        def __init__(self, **_kwargs: str) -> None:
            raise AssertionError("JSON files should not use the generic Docling loader")

    monkeypatch.setattr(loader, "DoclingLoader", UnexpectedLoader)

    documents = loader._load_file(str(source))

    assert len(documents) == 1
    assert json.loads(documents[0].page_content) == payload
    assert documents[0].metadata == {"source": str(source)}


def test_load_file_rejects_unallowlisted_extensions(tmp_path: Path) -> None:
    source = tmp_path / "program.bin"
    source.write_bytes(b"not a document")

    try:
        loader._load_file(str(source))
    except RuntimeError as error:
        assert str(error) == "Unsupported document type"
    else:
        raise AssertionError("Expected unsupported files to be rejected")
