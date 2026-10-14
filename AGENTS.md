# Repository Guidelines

## Project Structure & Module Organization

This is a Python 3.10–3.13 RAG application managed with `uv`. Runtime code is
under `src/`: loaders and document-type validation, ingestion and storage,
retrieval, chat, configuration, and S3/SQS event handling. Local ingestion
runs from `scripts/ingest_sources.py`. The browser chat is served by
`src/api/main.py`. Tests live in `tests/` and mirror the runtime modules. Local
input documents are in the ignored `sources/` directory (configurable with
`SOURCES_DIRECTORY`); design and operational notes are in `docs/`. Keep new
provider or domain logic in `src/` rather than in entry-point scripts.

## Build, Test, and Development Commands

Install or refresh the environment with `uv sync`. Run local ingestion with
`uv run ingest-sources`, then start the browser chat API with
`uv run uvicorn src.api.main:app --host 127.0.0.1 --port 8000`. Before
submitting changes, run:

```bash
uv run ruff check .
uv run pytest
```

Use `uv run pytest tests/test_loader.py` to iterate on one test module. Keep
`uv.lock` synchronized when dependencies change.

## Coding Style & Naming Conventions

Use four-space indentation, type annotations for public functions, and clear
`snake_case` names for modules, functions, and variables. Classes use
`PascalCase`; constants use `UPPER_SNAKE_CASE`. Ruff enforces an 88-character
line limit. Prefer small, composable functions and explicit configuration via
environment variables. Keep S3 and local ingestion on the shared document-type
allowlist.

## Testing Guidelines

Tests use pytest and are named `tests/test_<module>.py` with `test_*` functions.
Add regression coverage for changed behavior, including malformed input and
event validation where applicable. The complete suite is the required gate;
there is no configured coverage threshold.

## Commit & Pull Request Guidelines

For every issue-based or ad hoc repository change, read and follow
`skills/project-workflow/SKILL.md` before implementation. It governs issue
review, project status, branching, verification, and pull-request handoff.
Use `skills/gitlab-commit/SKILL.md` and `skills/pull-request/SKILL.md` for the
commit and PR steps it requires.

Never edit, stage, commit, or push changes directly on `master`. The project
uses feature branches and `master` is protected. Create or switch to an
issue-specific feature branch before making changes, and merge through a pull
request.

Use an imperative, capitalized commit subject of at least three words and no
more than 72 characters, without a trailing period (for example, `Add S3
ingestion tests`). Add a wrapped body when context is useful. Pull requests
must have a concise title and one or two prose paragraphs in the Description;
do not use bullets there. Artifacts only when useful review evidence exists.

## Security & Configuration Tips

Never commit `.env` files, API keys, cloud credentials, or generated vector
stores. Use `.env.example` as the configuration reference. S3 ingestion is
designed for S3 → SQS → Lambda delivery; preserve event validation, bounded
temporary files, and the configured maximum document size when changing it.
