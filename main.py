"""Compatibility entry point announcing retirement of the query CLI."""


def main() -> None:
    print(
        "The interactive query CLI is retired. Start the browser chat with: "
        "uv run uvicorn src.api.main:app --host 127.0.0.1 --port 8000"
    )


if __name__ == "__main__":
    main()
