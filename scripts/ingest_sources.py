from src.config import Settings
from src.domain import DocumentStatus
from src.ingestion import create_ingestion_service


def main() -> None:
    results = create_ingestion_service(Settings.from_env()).ingest_sources()
    for result in results:
        document = result.document
        if document.status is DocumentStatus.READY:
            action = "indexed" if result.indexed else "unchanged"
            print(
                f"{document.display_name}: {action} (version {document.index_version})"
            )
        else:
            print(f"{document.display_name}: failed ({document.error_code})")


if __name__ == "__main__":
    main()
