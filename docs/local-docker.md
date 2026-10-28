# Local Docker stack

The web image and PostgreSQL pgvector service run entirely in Docker. Docker
Desktop on an Intel Mac is sufficient; PostgreSQL and pgvector do not need to
be installed on the host. The existing root `Dockerfile` remains the separate
Lambda image. `Dockerfile.web` is the browser/API image, and its default target
is the web runtime. It uses the OpenCV headless wheel so the image does not need
desktop OpenGL system packages.

## Configure and start

Copy `.env.docker.example` to the ignored `.env.docker` file. Replace the
local database password and bearer token with your own values. The password
must be URL-safe because Compose constructs `DATABASE_URL` from it. The bearer
token must have at least 32 characters. Add `OPENAI_API_KEY` when you want to
ingest actual documents or generate chat answers. Keep `.env.docker` out of
Git and never pass its contents into issue or PR comments.

Run these commands from the repository root:

```bash
cp .env.docker.example .env.docker
docker compose --env-file .env.docker build web
docker compose --env-file .env.docker up -d db
docker compose --env-file .env.docker run --rm web alembic upgrade head
docker compose --env-file .env.docker up -d web
docker compose --env-file .env.docker exec web python -m src.profile_admin owner@example.com
docker compose --env-file .env.docker exec web python -m scripts.local_stack_smoke
```

The migration command uses Alembic directly because the local `db` CLI guards
against database URLs with non-loopback hosts. The browser is available at
`http://127.0.0.1:8000` unless `LOCAL_WEB_PORT` changes. The smoke command
checks database connectivity, the served browser, unauthorized and authorized
profile requests, and real document ingestion and pgvector retrieval. It uses
test embeddings so it does not call OpenAI, and removes its test document.
Provision the owner only once for a new database volume.

For ordinary ingestion, put supported files in the ignored `sources/` directory
and run:

```bash
docker compose --env-file .env.docker exec web python -m scripts.ingest_sources
```

The source directory is mounted read-only at `/app/sources`. The application
uses the same PostgreSQL database for the document registry and vectors. Its
browser/API also reads that database. Set a real OpenAI key in `.env.docker`
before this ingestion command or generating chat answers.

## Test and inspect

The optional test profile uses a separate temporary pgvector database, so its
migration test cannot drop the web service's vector table:

```bash
docker compose --env-file .env.docker --profile test build test
docker compose --env-file .env.docker --profile test run --rm test
docker compose --env-file .env.docker logs --tail=100 web db
docker compose --env-file .env.docker ps
```

The browser JavaScript test skips in the Python test image because Node.js is
not installed there; the repository CI runs it separately. To stop the stack
while retaining the database volume, run
`docker compose --env-file .env.docker --profile test down`. Add `--volumes`
only when you intend to delete the local database contents.

## Render handoff

For #86, prefer a [Git-backed Render web service](https://render.com/docs/docker)
using `Dockerfile.web`. Render builds this Dockerfile when the linked repository
deploys, and its default target runs the web app on port 10000 unless `PORT` is
configured. The Compose database
is only for local development; #86 configures the shared Neon database and
deployment secrets. A [prebuilt-image Render service](https://render.com/docs/deploying-an-image)
is also supported, but a new image push does not trigger an automatic
deployment without a separate deploy action. No Render or Neon resources are
created by this workflow.
