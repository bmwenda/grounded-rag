# Optional example: Render and Neon

This is one low-cost hosting configuration, chosen for a demonstration. Neither
provider is required: any compatible web host and PostgreSQL/pgvector database
can be used. Start with the [general deployment instructions](../README.md#deployment).

## Deploy and configure

Create a Free Neon project and database, then create a Render Blueprint from
`render.yaml`. It builds `Dockerfile` and runs Uvicorn on `0.0.0.0:$PORT` in
Oregon. `Dockerfile.lambda` is the separate AWS ingestion build. The service
name is `grounded-rag`; use the HTTPS URL assigned in the Render dashboard.

Enter these values in Render's Environment settings, never in Git:

| Setting | Value |
| --- | --- |
| `DATABASE_URL` | Neon connection URI for the application database, preserving `sslmode=require` and any other supplied TLS parameters |
| `OPENAI_API_KEY` | OpenAI API key |
| `OPENAI_MODEL` | Chat model available to the account |
| `API_BEARER_TOKEN` | Blueprint-generated secret; reveal it in Environment and paste its raw value into the browser login |
| `OPENAI_EMBEDDING_MODEL` | Optional; default `text-embedding-3-large`, matching the schema's 3,072 dimensions |

Lambda reads `DATABASE_URL`, `OPENAI_API_KEY`, and `OPENAI_MODEL` from the JSON
secret referenced by `runtime_secret_arn` in OpenTofu. Use the same Neon project,
branch, and database for both services, and the same embedding model. Lambda
writes chunks directly to Neon; Render retrieves them without an HTTP callback.
Keep the Neon database and TLS settings consistent even if using separate
pooled and direct connection endpoints. Do not put credentials in commands,
logs, screenshots, or the PR.

## Migrations and owner

Render Free has no pre-deploy command or dashboard shell. From the matching
local checkout, put the Neon URL in your ignored `.env` (ensure an exported
`DATABASE_URL` does not override it), then run:

```bash
uv run alembic upgrade head
uv run alembic current
uv run profile-admin owner@example.com
```

Use a database owner role permitted to create the vector extension. The
migration enables pgvector if needed. `current` should report `(head)`.
Run `upgrade head` before each deployment requiring new schema; it applies only
pending revisions. The `db` helpers intentionally restrict operations to local
PostgreSQL. A database connectivity probe is:

```bash
uv run python healthcheck.py
```

## AWS ingestion smoke test

Before testing, build the current `Dockerfile.lambda`, push a fresh ECR tag,
and apply its raw `sha256:...` digest through `image_digest`. Pushing an image
alone does not update Lambda. Confirm the runtime secret is configured and the
SQS event source mapping is enabled. See [AWS infrastructure](../infra/README.md).

1. Log into the Render app with the generated token and confirm chat works.
   Confirm an invalid token is rejected.
2. Create a small `.txt` document with a unique fact, for example
   `The Grounded RAG smoke-test code is CEDAR-7319.` Record its S3 key.
3. Upload it under the configured prefix (default `incoming`):

   ```bash
   SOURCE_BUCKET=$(tofu -chdir=infra output -raw source_bucket_name)
   aws s3 cp ./smoke-test.txt "s3://$SOURCE_BUCKET/incoming/smoke-test.txt"
   ```

4. Inspect Lambda CloudWatch logs, the SQS queue, and its dead-letter queue.
   Confirm successful ingestion rather than assuming delivery implies success.
5. In Neon SQL Editor, verify rows for the document and inspect chunk counts:

   ```sql
   SELECT count(*) AS chunks FROM document_chunks;
   ```

6. Ask the browser chat for the smoke-test code. Confirm `CEDAR-7319` and a
   citation to the uploaded document. Record date, deployed digest, S3 key,
   processing result, and answer/citation in the PR without secrets.

If processing fails, record the exception and blocking issue. Fix the worker,
then retry queued messages or redrive the DLQ. Earlier Chroma/read-only filesystem
traces indicate an outdated worker image; deploy the current pgvector image.

## Limits and usage

[Render Free](https://render.com/docs/free) sleeps after 15 minutes of inactivity;
the next request can take about a minute to wake it. Files disappear on restart,
redeploy, or sleep. Keep documents in S3 and all durable application data in
Neon. No paid Render plan or persistent disk is required. Inspect Render Billing
for instance hours, bandwidth, and build usage; inspect service logs for errors.

Check the Neon project's Usage dashboard and
[current plan limits](https://neon.com/docs/introduction/plans) before ingestion;
The current Free allowance is 1 GB of PostgreSQL storage per project
(20 GB across the account); embeddings consume substantial space. The dashboard
is authoritative for the project's allowance. Inspect database and vector sizes:

```sql
SELECT pg_size_pretty(pg_database_size(current_database()));
SELECT count(*), pg_size_pretty(pg_total_relation_size('document_chunks'))
FROM document_chunks;
```

Inspect AWS Billing/Cost Explorer, SQS/DLQ depth, Lambda errors and duration, and
OpenAI usage separately; these are not covered by Render/Neon allowances.

## Export, restore, and rebuild

Keep source documents independently of the vector database. Before schema changes
or cleanup, use a direct Neon connection and PostgreSQL client tools matching the
server version. Configure a local libpq service named `neon-demo` and a protected
password file outside Git; use the standard `postgresql` connection scheme:

```bash
pg_dump --dbname=service=neon-demo --format=custom --file=/tmp/grounded-rag.dump
```

The dump contains chat and document data: store it privately outside the repo.
To restore, create an empty Neon database, configure a second libpq service
`neon-restore`, enable vector there, and run:

```bash
pg_restore --dbname=service=neon-restore --no-owner --no-privileges /tmp/grounded-rag.dump
```

Validate the restored schema and data before changing either service's database
URL. To rebuild disposable data instead, create an empty database, run migrations
and provision the owner, point Render and Lambda at it, then re-upload retained
sources under the allowed prefix. This recreates vectors and incurs embedding
usage; it does not recover old chat history. Do not use `alembic stamp` on an
empty database.

## Stop or delete

To pause ingestion, disable the Lambda SQS trigger and stop uploading; queued
messages still have a retention deadline. Suspend the Render service from its
dashboard. For full teardown, export data and retain required source documents,
then delete the Render service/Blueprint and the Neon project from their
respective dashboards. These deletes remove data and require deliberate review.
For AWS teardown, follow `infra/README.md`, review an OpenTofu destroy plan with
the same variable file, and resolve nonempty S3/ECR resources deliberately. Remove
unused secrets and verify billing afterward. Deleting Render or Neon does not
remove AWS resources or stop Lambda retries.
