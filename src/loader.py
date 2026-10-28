import glob
import json
import logging
import os
from pathlib import Path

# Docling imports optional transformer integrations. This keeps their optional-model
# notices out of the CLI while conversion errors still propagate to ingestion.
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
logging.getLogger("docling").setLevel(logging.ERROR)

from langchain_core.documents import Document
from langchain_docling.loader import DoclingLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

from .config import sources_directory_from_env
from .document_types import is_supported_document


def _load_file(file_path: str) -> list[Document]:
    """Load an allowed document with the maintained generic file loader."""
    if not is_supported_document(file_path):
        raise RuntimeError("Unsupported document type")
    if Path(file_path).suffix.lower() == ".json":
        content = json.loads(Path(file_path).read_text(encoding="utf-8-sig"))
        return [
            Document(
                page_content=json.dumps(content, ensure_ascii=False, indent=2),
                metadata={"source": file_path},
            )
        ]
    return DoclingLoader(file_path=file_path).load()


def load_and_chunk_sources(
    sources_dir: str | None = None,
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
) -> tuple[list[Document], list[str], list[str]]:
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )

    directory = sources_dir if sources_dir is not None else sources_directory_from_env()
    file_paths = sorted(
        path
        for path in glob.glob(os.path.join(directory, "*"))
        if os.path.isfile(path)
    )

    all_chunks: list[Document] = []
    all_ids: list[str] = []
    source_files: list[str] = []

    for file_path in file_paths:
        base_name = os.path.basename(file_path)
        source_id = base_name.replace(".", "_")
        chunks, chunk_ids = load_and_chunk_file(
            file_path,
            document_id=source_id,
            index_version=0,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            text_splitter=text_splitter,
        )
        if chunks:
            all_chunks.extend(chunks)
            all_ids.extend(chunk_ids)
            source_files.append(base_name)

    return all_chunks, all_ids, source_files


def load_and_chunk_file(
    file_path: str,
    *,
    document_id: str,
    index_version: int,
    source_uri: str | None = None,
    display_name: str | None = None,
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
    text_splitter: RecursiveCharacterTextSplitter | None = None,
) -> tuple[list[Document], list[str]]:
    """Load one file into versioned chunks while preserving source provenance."""
    documents = _load_file(file_path)
    if not documents:
        return [], []

    splitter = text_splitter or RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    split_chunks = splitter.split_documents(documents)
    base_name = display_name or os.path.basename(file_path)
    chunks: list[Document] = []
    chunk_ids: list[str] = []

    for index, chunk in enumerate(split_chunks):
        metadata = {
            **{
                key: json.dumps(value)
                if isinstance(value, (dict, list, tuple))
                else value
                for key, value in chunk.metadata.items()
            },
            "document_id": document_id,
            "display_name": base_name,
            "source": source_uri or file_path,
            "index_version": index_version,
            "chunk_index": index,
        }
        page = metadata.get("page")
        if isinstance(page, int):
            metadata["page_number"] = page + 1

        chunks.append(Document(page_content=chunk.page_content, metadata=metadata))
        chunk_ids.append(f"{document_id}:{index_version}:{index}")

    return chunks, chunk_ids
