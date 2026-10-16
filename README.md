## Description

This is a simple Retrieval-Augmented Generation (RAG) application for searching
an organization's knowledge base through an authenticated browser chat. It
combines document ingestion, embedding, and retrieval to provide source-backed
answers.

The implemented capabilities, deployment constraints, and remaining delivery
tasks are maintained in the [product and delivery specification](docs/specification.md).

## Key Technologies

- **LangChain** - LLM framework for building RAG pipelines
- **OpenAI Embeddings** - Semantic text embeddings for understanding document meaning
- **Chroma** - Vector database for efficient document storage and retrieval
- **SQLAlchemy** - ORM persistence for document identity and ingestion state
- **DoclingLoader** - Parses PDF, text, Markdown, HTML, Office, and other
  supported document formats
- **RecursiveCharacterTextSplitter** - Intelligent document chunking with overlap

## How It Works

1. **Load Documents** - Place supported documents, such as PDF, text, Markdown,
   HTML, or Office files, in the `sources/` folder
2. **Process & Chunk** - Documents are automatically split into overlapping chunks for better retrieval
3. **Generate Embeddings** - Each chunk is converted into semantic embeddings using OpenAI
4. **Store in Vector DB** - Embeddings are stored in Chroma for fast similarity search
5. **Retrieve & Query** - Search for relevant documents using natural language queries

## Installation

### Prerequisites
- Python 3.12
- OpenAI API key
- PostgreSQL database for the document registry

### Steps

1. **Clone the repository and navigate to the project:**
   ```bash
   cd simple-rag
   ```

2. **Install dependencies using uv:**
   ```bash
   uv sync
   ```

3. **Set up environment variables:**
   Create a `.env` file in the project root:
   ```
   OPENAI_API_KEY=your-api-key-here
   OPENAI_MODEL=gpt-4-turbo
   DATABASE_URL=postgresql+psycopg://rag_user:change_me@localhost:5432/simple_rag
   ```

   For local development, use a PostgreSQL role with permission to create
   databases. See `.env.example` for optional embedding, Chroma, retrieval, and
   chunking settings.

   Prepare the local database and apply pending schema migrations:
   ```bash
   uv run db prepare
   ```

4. **Add documents:**
   Create the local source directory:
   ```bash
   mkdir -p sources
   ```
   Place supported documents, such as PDF, text, Markdown, HTML, or Office
   files, in the `sources/` folder. These files are local inputs and are ignored
   by Git. Set `SOURCES_DIRECTORY` in `.env` to use another directory; relative
   paths are resolved from the project root, and absolute paths are supported.
   Create the configured directory before ingestion. If a custom directory is
   inside the repository, add it to `.git/info/exclude` to keep it local.

5. **Ingest documents:**
   ```bash
   uv run ingest-sources
   ```

## Usage

### Ingest Documents

```bash
uv run ingest-sources
```

Each source receives a persistent document identity and checksum in the
PostgreSQL registry. Re-running ingestion skips unchanged documents; changing a
file writes a new index version and removes the old chunks after the replacement
succeeds.
Failures are isolated to the affected document and retried according to
`INGESTION_MAX_ATTEMPTS`.

The `db` command provides local development tasks: `uv run db create` creates
the configured database, `uv run db migrate` applies pending Alembic migrations,
and `uv run db drop` asks for the database name before dropping it.
`uv run db prepare` creates the database if needed and applies migrations.
These commands require a local PostgreSQL URL; the role must have permission
to create or drop the database when using those commands. For an existing
database whose schema already matches the initial migration, run
`uv run alembic stamp head` once to establish its migration baseline. To
inspect the migration version, run `uv run alembic current`.

Before ingestion, the registry connects to PostgreSQL and checks that its
document table has the expected columns. To probe database connectivity without
an OpenAI key, run
`uv run python healthcheck.py`; it exits nonzero if the database query fails.

### Profile and chat API

After applying migrations, provision the first owner outside the API:

```bash
uv run profile-admin owner@example.com
```

Set `API_BEARER_TOKEN` in `.env` to a unique random value of at least 32
characters. Generate one with
`python -c 'import secrets; print(secrets.token_urlsafe(32))'`.

Start the API server from the project root after preparing the database and
provisioning the owner:

```bash
uv run uvicorn src.api.main:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/` for the browser chat. Enter the bearer token
to see your chats, ask questions, and expand source references on answers.
Use the menu beside a chat to rename or archive it. Archived chats remain
readable and can be reactivated from the Archived list.
The token is kept in browser session storage and cleared when you log out
or close the tab. The selected chat is restored after a reload in the same tab;
use New chat to begin a separate conversation. If sending fails, reload the
conversation before trying again: the question may already have been saved by
the API.

Send the token as `Authorization: Bearer <token>` to `/v1/users/me` and
`/v1/chats`. The first owner can update their email and name through
`GET`, `PATCH`, and `DELETE /v1/users/me`. Create a chat with
`POST /v1/chats` and a JSON body such as `{"content": "What is the policy?"}`.
Chat creation waits for an answer and requires the configured OpenAI model,
embedding key, and indexed documents. `GET /v1/chats` lists chats with optional
`status`, `cursor`, and `limit` query parameters; `GET`, `PATCH`, and `DELETE`
`/v1/chats/{id}` manage one chat. Deletion hides it immediately and records a
deletion timestamp for the retention process tracked in issue #47.

`GET /v1/chats/{id}/messages` returns messages in chronological order with
optional `cursor` and `limit` parameters. `POST /v1/chats/{id}/messages` accepts
`{"content": "Follow-up question"}` and waits for the assistant answer. The
server uses up to 12 recent messages to interpret a follow-up, while the
answer is grounded in retrieved documents. If generation fails, the submitted
question remains visible when the client reloads message history. A second
post to the same chat during answer generation returns `409`.

Deleting the owner immediately revokes this token's API access; later
retention work will purge deleted data.

There is no public registration route. A replaceable token verifier is tracked
separately in the Chat Interface backlog.

Deleted chats and users are physically removed by the host-scheduled
`uv run chat-retention` command. It is independent of the web process and only
requires `DATABASE_URL`, so the same command works with cron, AWS Batch,
Kubernetes CronJobs, and similar schedulers. See
[Chat-history retention](docs/chat-retention.md) for configuration, the
recommended six-hour schedule, AWS guidance, retries, and monitoring.

`src/api/main.py` builds the app and includes resource routers under `/v1`.
Place new HTTP handlers in `src/api/routers/`, request and response schemas in
`src/api/schemas/`, and shared authentication or service dependencies in
`src/api/dependencies.py`. Domain rules and persistence stay in their modules
under `src/`; the app lifespan manages profile and chat repositories.

### Ingest from an S3 source bucket

Set `S3_SOURCE_BUCKET`, optionally limit it with `S3_SOURCE_PREFIX`, and deploy
`src.s3_ingestion_handler.lambda_handler` behind an S3-to-SQS-to-Lambda
notification. The handler accepts only SQS-delivered S3 object-created events,
then streams each object to a bounded temporary file and ingests it under its
stable `s3://bucket/key` identity. See
[S3 source-bucket ingestion](docs/s3-ingestion.md) for IAM, event, and retry
guidance and [AWS infrastructure](infra/README.md) for the OpenTofu deployment.

### Ask questions in the browser

Start the API from the project root after preparing the database and
provisioning the owner:

```bash
uv run uvicorn src.api.main:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/` and enter the configured bearer token. Answers
include numbered source references, with PDF page numbers when available. If
no retrieved content meets the relevance threshold, the browser chat returns
an explicit no-answer response.

## Development

Run the complete local check suite:

```bash
uv run ruff check .
uv run mypy src/ scripts/
uv run pytest
```

Run an individual check:

```bash
uv run pytest tests/test_retriever.py
```
