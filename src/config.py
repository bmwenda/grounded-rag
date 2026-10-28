import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy.engine import URL

from .database import parse_database_url
from .domain import ConfigurationError

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCES_DIRECTORY = PROJECT_ROOT / "sources"


@dataclass(frozen=True)
class Settings:
    openai_api_key: str = field(repr=False)
    openai_model: str
    database_url: URL = field(repr=False)
    sources_directory: Path = DEFAULT_SOURCES_DIRECTORY
    embedding_model: str = "text-embedding-3-large"
    retrieval_count: int = 4
    retrieval_relevance_threshold: float = 0.2
    chunk_size: int = 1000
    chunk_overlap: int = 200
    embedding_batch_size: int = 100
    ingestion_max_attempts: int = 2
    s3_source_bucket: str | None = None
    s3_source_prefix: str = ""
    aws_region: str | None = None
    max_document_size_bytes: int = 100 * 1024 * 1024

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()
        settings = cls(
            openai_api_key=_required_env("OPENAI_API_KEY"),
            openai_model=_required_env("OPENAI_MODEL"),
            database_url=database_url_from_env(),
            sources_directory=sources_directory_from_env(),
            embedding_model=os.getenv(
                "OPENAI_EMBEDDING_MODEL", "text-embedding-3-large"
            ),
            retrieval_count=_integer_env("RETRIEVAL_COUNT", 4),
            retrieval_relevance_threshold=_float_env(
                "RETRIEVAL_RELEVANCE_THRESHOLD", 0.2
            ),
            chunk_size=_integer_env("CHUNK_SIZE", 1000),
            chunk_overlap=_integer_env("CHUNK_OVERLAP", 200),
            embedding_batch_size=_integer_env("EMBEDDING_BATCH_SIZE", 100),
            ingestion_max_attempts=_integer_env("INGESTION_MAX_ATTEMPTS", 2),
            s3_source_bucket=_optional_env("S3_SOURCE_BUCKET"),
            s3_source_prefix=os.getenv("S3_SOURCE_PREFIX", ""),
            aws_region=_optional_env("AWS_REGION"),
            max_document_size_bytes=_integer_env(
                "MAX_DOCUMENT_SIZE_BYTES", 100 * 1024 * 1024
            ),
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        if self.retrieval_count < 1:
            raise ConfigurationError("RETRIEVAL_COUNT must be at least 1")
        if not 0 <= self.retrieval_relevance_threshold <= 1:
            raise ConfigurationError(
                "RETRIEVAL_RELEVANCE_THRESHOLD must be between 0 and 1"
            )
        if self.chunk_size < 1:
            raise ConfigurationError("CHUNK_SIZE must be at least 1")
        if self.chunk_overlap < 0:
            raise ConfigurationError("CHUNK_OVERLAP cannot be negative")
        if self.chunk_overlap >= self.chunk_size:
            raise ConfigurationError("CHUNK_OVERLAP must be smaller than CHUNK_SIZE")
        if self.embedding_batch_size < 1:
            raise ConfigurationError("EMBEDDING_BATCH_SIZE must be at least 1")
        if self.ingestion_max_attempts < 1:
            raise ConfigurationError("INGESTION_MAX_ATTEMPTS must be at least 1")
        if self.max_document_size_bytes < 1:
            raise ConfigurationError("MAX_DOCUMENT_SIZE_BYTES must be at least 1")


def sources_directory_from_env() -> Path:
    load_dotenv()
    directory = Path(os.getenv("SOURCES_DIRECTORY", "sources"))
    return directory if directory.is_absolute() else PROJECT_ROOT / directory


def database_url_from_env() -> URL:
    load_dotenv()
    return parse_database_url(os.getenv("DATABASE_URL"))


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ConfigurationError(f"Missing required environment variable: {name}")
    return value


def _optional_env(name: str) -> str | None:
    value = os.getenv(name)
    return value if value else None


def _integer_env(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        return int(raw_value)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be an integer") from exc


def _float_env(name: str, default: float) -> float:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        return float(raw_value)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be a number") from exc
