# S3 source-bucket ingestion

The application can ingest documents uploaded to one private S3 source bucket.
It accepts allowlisted PDF, text, Markdown, HTML, Office, and other general
document formats from the configured prefix, reads object metadata before
downloading, rejects objects larger than the configured limit, and streams the
object to a temporary file. The temporary filename is never used as the document
identity: the registry tracks `s3://<bucket>/<key>`, so a new upload at the same
key replaces the prior index version.

## Configuration

Set the following environment variables in the Lambda/worker environment:

```text
S3_SOURCE_BUCKET=company-rag-sources
S3_SOURCE_PREFIX=incoming
AWS_REGION=eu-west-1
MAX_DOCUMENT_SIZE_BYTES=104857600
DATABASE_URL=postgresql+psycopg://rag_user:change_me@db-host:5432/simple_rag
```

`S3_SOURCE_PREFIX` may be empty to allow the whole bucket. The execution role
needs `s3:GetObject` and `s3:HeadObject` on the configured bucket and prefix,
plus read/write access to the configured vector store and document registry.
The worker must be able to connect to PostgreSQL before processing messages;
use `uv run python healthcheck.py` for a database connectivity probe.
Keep the bucket private and enable server-side encryption.

## Event delivery

Deploy `src.s3_ingestion_handler.lambda_handler` as the worker entrypoint.
Configure S3 event notifications for `s3:ObjectCreated:*` to deliver to SQS,
then configure Lambda with that SQS queue as its event source. Apply the
configured prefix and the extensions in `SUPPORTED_DOCUMENT_EXTENSIONS` on the
S3 notification. The handler intentionally accepts only SQS-delivered S3 event
payloads; direct S3 to Lambda delivery is unsupported.

Configure a dead-letter queue and set the Lambda visibility timeout longer than
the largest expected document ingestion time. The handler returns a compact
status payload and never returns raw exception details.

The baseline AWS resources are defined with OpenTofu under `infra/`. See the
[infrastructure guide](../infra/README.md) for inputs, validation, planning,
and deployment. S3 object-created notification filters are tracked separately
and are not part of the baseline module.

## Local verification

Unit tests use an in-memory S3 client fake; no AWS credentials or network calls
are required. Before deployment, verify the bucket notification, IAM role, and
SQS retry/DLQ behavior in an AWS account or an S3-compatible integration test
environment.
