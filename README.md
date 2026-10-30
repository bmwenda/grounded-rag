# Grounded RAG

**Your organization's documents. Answers you can trace.**

Grounded RAG turns company knowledge into an authenticated, conversational
workspace. Ask questions in plain language and get answers grounded in indexed
documents, with numbered citations you can inspect. When retrieval finds no
relevant evidence, it explicitly says: “The available documents do not contain
that information.” The answer pipeline rejects missing or unknown citations to keep source
references verifiable.

- **Check the source:** citations identify the document and page or chunk behind
  an answer.
- **Choose your chat model:** native OpenAI-compatible, Anthropic, and Ollama
  support, including open-weight models hosted through Ollama.
- **Bring your documents:** ingest PDFs, text, Markdown, HTML, Office files,
  and other supported formats locally or through S3 → SQS → Lambda.
- **Keep knowledge current:** checksum-based ingestion skips unchanged files
  and replaces indexed chunks when a document changes.
- **Continue the conversation:** browser chat supports follow-up questions,
  saved history, renaming, and archiving.
- **Deploy on your terms:** PostgreSQL with pgvector shares durable document,
  vector, and chat storage across ingestion and the web app. Choose your own
  compatible web and database hosts.

See the [product and delivery specification](docs/specification.md) for
implemented capabilities and planned work.

## Key Technologies

- **LangChain** - LLM framework for building RAG pipelines
- **Embedding model** - Semantic text embeddings for understanding document meaning
- **PostgreSQL pgvector** - Shared vector and document storage for ingestion and chat
- **SQLAlchemy** - ORM persistence for document identity, chunks, and ingestion state
- **DoclingLoader** - Parses PDF, text, Markdown, HTML, Office, and other
  supported document formats
- **RecursiveCharacterTextSplitter** - Intelligent document chunking with overlap

## How It Works

1. **Load Documents** - Place supported documents, such as PDF, text, Markdown,
   HTML, or Office files, in the `sources/` folder
2. **Process & Chunk** - Documents are automatically split into overlapping chunks for better retrieval
3. **Generate Embeddings** - Each chunk is converted into semantic embeddings using the configured embedding model
4. **Store in Vector DB** - Embeddings are stored in PostgreSQL pgvector
5. **Retrieve & Query** - Search for relevant documents using natural language queries

## Installation

### Prerequisites

- Python 3.12
- LLM API credentials
- PostgreSQL database with the pgvector extension available
- AWS S3, SQS, and Lambda for the AWS ingestion pipeline (local ingestion also works)

The web app and database can run on any compatible host. Chat supports OpenAI-compatible APIs, Anthropic, and Ollama; embeddings use
an OpenAI-compatible endpoint;
hosting providers are your choice.

### Steps

1. **Clone the repository and navigate to the project:**
   ```bash
   git clone https://github.com/bmwenda/grounded-rag.git
   cd grounded-rag
   ```

2. **Install dependencies using uv:**
   ```bash
   uv sync
   ```

3. **Set up environment variables:**
   Create a `.env` file in the project root:
   ```
   LLM_API_KEY=your-api-key-here
   LLM_MODEL=gpt-4-turbo
   DATABASE_URL=postgresql+psycopg://rag_user:change_me@localhost:5432/grounded_rag
   ```

   For local development, use a PostgreSQL role with permission to create
   databases. See `.env.example` for optional embedding, retrieval, and
   chunking settings.

   The migration enables pgvector and creates `document_chunks`. It requires a
   database role allowed to create the extension. The current schema uses
   3,072-dimensional embeddings, matching `text-embedding-3-large`. Keep the
   embedding model compatible with that dimension. Local ingestion, S3 ingestion,
   and chat retrieval must use the same `DATABASE_URL`.

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

### Vector storage capacity

Size your database for documents, embeddings, and chat history. Check database
and vector table sizes before increasing the corpus:

```sql
SELECT pg_size_pretty(pg_database_size(current_database())) AS database_size;
SELECT count(*) AS chunks,
       pg_size_pretty(pg_total_relation_size('document_chunks')) AS total_size
FROM document_chunks;
```

The initial pgvector query uses exact cosine search without an approximate
index. Its relevance score is cosine similarity clamped to 0–1; the default
`RETRIEVAL_RELEVANCE_THRESHOLD=0.2` now applies to that scale. Benchmark
latency and storage growth before increasing the demo corpus.

For an isolated integration check, start a disposable pgvector PostgreSQL
instance and set `PGVECTOR_TEST_DATABASE_URL` to its database URL. Then run
`uv run pytest tests/test_vector_store.py`. The test applies migrations and
checks insertion, search, replacement, and deletion. Use only a disposable
database for this test.

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
a model API key, run
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
Chat creation waits for an answer and requires the configured chat model,
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

## Local development

### Docker stack

The default `Dockerfile` builds the web/API image. `Dockerfile.lambda` builds
the separate AWS Lambda image. Docker Desktop runs the app and pgvector without
installing PostgreSQL on the host. If you do not already have `.env`, copy
`.env.example` to `.env`; set `LOCAL_POSTGRES_PASSWORD` to a URL-safe value and
`API_BEARER_TOKEN` to at least 32 characters. Compose reads `.env` from the
repository root.

```bash
docker compose build web
docker compose up -d db
docker compose run --rm web alembic upgrade head
docker compose up -d web
docker compose exec web profile-admin owner@example.com
docker compose exec web python -m scripts.local_stack_smoke
docker compose exec web ingest-sources
docker compose --profile test build test
docker compose --profile test run --rm test
docker compose logs --tail=100 web db
docker compose --profile test down
```

The migration command uses Alembic directly because the local `db` command
requires a loopback database host. The web app and ingestion use the same
PostgreSQL database. The browser is at `http://127.0.0.1:8000` by default;
`LOCAL_WEB_PORT` changes the host port. The `sources/` directory is mounted
read-only. The smoke check uses test embeddings and removes its test document.
Docling caches tokenizer and OCR models in persistent volumes; the
unauthenticated HF Hub notice is a rate-limit warning. Add a real
`LLM_API_KEY` before real ingestion or chat. `down` stops the stack but keeps
the database and model-cache volumes; add `--volumes` only to delete local data
and cached models.

## Deployment

Run the web image on any container host, or run Uvicorn directly. Provide
PostgreSQL with pgvector and configure these environment variables through your
host's secret management:

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | PostgreSQL connection URI; preserve the database's required TLS parameters |
| `LLM_API_KEY` | API key for the configured model endpoint |
| `LLM_MODEL` | Chat model served by your endpoint |
| `API_BEARER_TOKEN` | Random login token of at least 32 characters |
| `EMBEDDING_MODEL` | Optional; defaults to `text-embedding-3-large` (3,072 dimensions) |
| `PORT` | Container HTTP port; defaults to `10000` |

Select `LLM_PROVIDER=openai` (default), `anthropic`, or `ollama`. The selected
provider uses its native chat API. Set `LLM_MODEL` to a model served by that
provider and `LLM_BASE_URL` to an optional custom endpoint.

| Provider | Chat configuration |
| --- | --- |
| OpenAI-compatible | `LLM_PROVIDER=openai`, `LLM_MODEL`, `LLM_API_KEY`; optional `LLM_BASE_URL` |
| Anthropic | `LLM_PROVIDER=anthropic`, `LLM_MODEL`, `LLM_API_KEY` with an Anthropic key |
| Ollama | `LLM_PROVIDER=ollama`, `LLM_MODEL=llama3.2`; no chat key required; endpoint defaults to `http://localhost:11434` |

For open-weight chat, install Ollama separately, run `ollama pull llama3.2`, and
start its server. The app does not download or host model weights. In containers,
configure a reachable Ollama endpoint rather than container-local localhost.

Embeddings use an independent OpenAI-compatible service. For Anthropic or
Ollama chat, set `EMBEDDING_API_KEY` and optionally `EMBEDDING_BASE_URL`;
chat credentials and endpoints are not reused. For OpenAI-compatible chat,
embeddings default to the chat key and endpoint unless overridden.
Set `EMBEDDING_MODEL` to a model returning 3,072 dimensions, as required by the
current schema. Changing dimensions requires a migration and re-ingestion.
The default embedding endpoint and model remain OpenAI's. Other native chat
protocols need an adapter.

Lambda runtime secrets use the same generic setting names and accept the
optional endpoint settings.

Use the same database and embedding model for ingestion and retrieval. See
`.env.example` for optional settings. Keep credentials outside Git and serve
the app over HTTPS through your host or reverse proxy.

For an existing database, apply migrations and provision the owner before
serving traffic:

```bash
uv run alembic upgrade head
uv run alembic current
uv run profile-admin owner@example.com
```

These commands use `DATABASE_URL`. Migrations require permission to enable
pgvector, unless an administrator has already enabled it. Repeat `upgrade head`
when deploying schema changes; the owner command provisions application data
without a separate seed fixture. In the web image, run these commands without
`uv run`. The image starts Uvicorn on `0.0.0.0:$PORT`.

For AWS ingestion, configure the bucket, prefix, queue, Lambda image, and runtime
secret as described in [AWS infrastructure](infra/README.md). Schedule
[chat retention](docs/chat-retention.md) independently of the web process.
Monitor database capacity and back up application data and source documents
using your chosen provider's tools or PostgreSQL exports.

## Verification

### Python checks

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
