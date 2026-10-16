# Simple RAG product and delivery specification

Status: Active backlog

Last verified against code and GitHub issues: 2026-10-14

## Purpose

Simple RAG lets an organization's users ask questions over its indexed
knowledge and inspect citations from the retrieved source material. Answers
must stay grounded in that material. Ingestion must be safe to retry without
leaving duplicate or stale vector chunks.

This is the active product specification. Shipped capabilities are summarized
as the current baseline; unchecked items below describe work that remains.
Each open delivery item links to its GitHub issue.

## Current baseline

- A browser chat is the primary user interface. FastAPI serves the static chat
  page and versioned profile, chat, and message routes under `/v1`.
- The first release provisions one owner administratively and protects API
  requests with `API_BEARER_TOKEN`. The browser keeps that token for its tab
  session. There is no public registration or multi-tenant identity provider.
- Chats, messages, citation snapshots, and profile data are stored in
  PostgreSQL. Chat and profile deletion immediately hides the content and
  schedules physical deletion; `chat-retention` can purge due records in
  bounded batches. The example host scheduler is in
  `deploy/cron/chat-retention.cron.example`.
- Chat history supports follow-up questions, archived and active chats,
  renaming, deletion, and citation snapshots. Answers validate citations
  against retrieved source chunks and return sanitized service errors.
- Local documents can be ingested with `uv run ingest-sources`. S3 objects can
  be ingested through the SQS event handler; direct S3-to-Lambda payloads are
  rejected. Both paths use the shared ingestion service and PostgreSQL
  document registry.
- The document registry uses SQLAlchemy and Alembic. It records document
  checksums, status, version, chunk count, retry count, and safe error codes.
  Ingestion is idempotent for unchanged ready documents and retries failed
  vector writes, but it has no durable job queue, attempt history, or worker
  lease.
- Chroma currently uses a local persistent directory. It is not configured as
  a horizontally scalable production service.
- S3 ingestion checks the configured object-size limit before download and
  validates the configured bucket, prefix, and supported file extension.
  Upload URLs, document upload/status/deletion routes, production AWS
  infrastructure, and document retention policy are not implemented.
- The interactive query CLI has been retired. S3 event processing still
  requires S3 -> SQS -> Lambda; deployed notifications and infrastructure are
  not yet provisioned by this repository.

## Supported documents and operating limits

- Supported document extensions are maintained in `src/document_types.py`.
- `MAX_DOCUMENT_SIZE_BYTES` defaults to 100 MiB (104,857,600 bytes) and is
  configurable. The S3 pre-download boundary enforces it today. The future
  upload API must enforce it at every upload boundary.
- A document should become searchable within five minutes of upload
  completion. The end-to-end target has not yet been measured or enforced.
- The first browser release supports one administratively provisioned owner.
  Multi-user identity and tenancy are out of scope until explicitly planned.
- Chat and profile content must become inaccessible immediately when deleted
  and be physically purged within 30 days. The scheduled purge runs after 29
  days to leave operational margin.
- User-visible failures must remain sanitized; credentials, document content,
  and raw backend exceptions must not be exposed in responses or logs.

## Architecture contract

```text
local files -> ingest-sources ------------------------+
                                                     +-> ingestion service
S3 source bucket -> SQS -> Lambda -------------------+       -> validate -> parse -> chunk
                                                             -> embed -> Chroma + PostgreSQL registry

browser -> FastAPI static chat + authenticated /v1 API -> chat service
                                                       -> retrieve -> grounded answer + citations
                                                       -> PostgreSQL profile/chat/message history

scheduled chat-retention command -> PostgreSQL soft-deleted profiles and chats
```

Stable vector IDs use `{document_id}:{index_version}:{chunk_index}`. Citation
metadata must retain `document_id`, display name, source URI, page number when
available, and index version. API citation snapshots expose only the documented
user-facing fields.

## Delivery backlog

### P0 — deliver the document upload and lifecycle API

- [ ] [Measure and meet the five-minute searchable target for a 100 MiB
  document](https://github.com/bmwenda/simple-rag/issues/8). Define bounded
  retries or failure when the target cannot be met.
- [ ] [Define document lifecycle transitions and retry
  rules](https://github.com/bmwenda/simple-rag/issues/9), including upload,
  processing, ready, failed, deleting, and deleted states.
- [ ] [Unify local and S3 document storage behind an
  abstraction](https://github.com/bmwenda/simple-rag/issues/10) so ingestion
  services do not depend on local paths or S3-specific types.
- [ ] [Create upload, status, and deletion application
  services](https://github.com/bmwenda/simple-rag/issues/11), with recoverable
  document deletion across object storage, vector chunks, and the registry.
- [ ] [Issue scoped, short-lived upload
  URLs](https://github.com/bmwenda/simple-rag/issues/12) for configured storage
  locations; callers must not choose arbitrary buckets or object keys.
- [ ] [Support multipart uploads when the configured size threshold
  requires them](https://github.com/bmwenda/simple-rag/issues/13), including
  completion, abort, and abandoned-upload cleanup.
- [ ] [Validate uploads before indexing](https://github.com/bmwenda/simple-rag/issues/14):
  extension, detected content type, size, checksum, normalized display name,
  and the malware-scanning integration point.
- [ ] [Delete documents through a recoverable
  workflow](https://github.com/bmwenda/simple-rag/issues/15), removing the
  source object, every indexed chunk version, and the registry record.
- [ ] [Expose versioned HTTP routes for document upload, completion, status,
  deletion, and service health](https://github.com/bmwenda/simple-rag/issues/36).
  Enforce `MAX_DOCUMENT_SIZE_BYTES` at each upload boundary, return documented
  responses, and sanitize errors.

Definition of done: an authorized user can upload, track, retry, search, and
delete a document without leaving an orphaned source object, registry record,
or vector chunk. Size limits apply at every upload and ingestion boundary.

### P1 — make AWS event ingestion deployable and operable

- [ ] [Provision the private source bucket, SQS queue, Lambda mapping, dead
  letter queue, encryption, and least-privilege IAM with
  OpenTofu](https://github.com/bmwenda/simple-rag/issues/16).
- [ ] [Configure S3 object-created notifications and supported-document
  filters](https://github.com/bmwenda/simple-rag/issues/17), delivering only
  to the ingestion queue.
- [ ] [Report partial SQS batch
  failures](https://github.com/bmwenda/simple-rag/issues/18) so successful
  records are not retried with failed records.
- [ ] [Set queue and Lambda timeouts, retries, concurrency, and dead letter
  retention](https://github.com/bmwenda/simple-rag/issues/19) to support the
  configured size limit and searchable-time target.
- [ ] [Size Lambda memory and ephemeral storage for the supported parsing
  workload](https://github.com/bmwenda/simple-rag/issues/20) and verify it
  against the five-minute target.
- [ ] [Emit structured, sanitized ingestion
  logs](https://github.com/bmwenda/simple-rag/issues/21) with document and SQS
  identifiers, without credentials or document content.
- [ ] [Publish operational metrics and
  alarms](https://github.com/bmwenda/simple-rag/issues/22) for queue age, dead
  letter depth, outcomes, object size, parsing, chunking, embedding latency,
  and retries.
- [ ] [Exercise the complete S3 -> SQS -> Lambda path in an AWS or compatible
  integration environment](https://github.com/bmwenda/simple-rag/issues/23).
- [ ] [Generate large-document integration coverage for bounded memory and
  object-size enforcement](https://github.com/bmwenda/simple-rag/issues/24).

Definition of done: operators can deploy and observe the event path, safely
retry failures, and handle poison messages without manual local ingestion.

### P1 — complete durable ingestion coordination

- [ ] [Persist ingestion jobs, attempts, leases, and ownership boundaries in
  PostgreSQL](https://github.com/bmwenda/simple-rag/issues/25). SQLAlchemy,
  Alembic, and the existing document registry are already in place; this item
  covers the remaining coordination model.
- [ ] [Claim ingestion work transactionally with expiring
  leases](https://github.com/bmwenda/simple-rag/issues/28) so concurrent
  workers cannot index the same document version.
- [ ] [Add PostgreSQL-backed integration coverage for idempotency, concurrent
  claims, retries, migrations, startup validation, and
  health](https://github.com/bmwenda/simple-rag/issues/30).

Definition of done: ingestion work and recovery decisions are durable,
coordinated across workers, and verified against PostgreSQL.

### P1 — prepare vector storage for production use

- [ ] [Document the supported Chroma topology, persistence, backup, restore,
  and scaling limits](https://github.com/bmwenda/simple-rag/issues/31).
- [ ] [Externalize Chroma connection, authentication, collection, and
  persistence configuration](https://github.com/bmwenda/simple-rag/issues/32)
  and validate it at startup.
- [ ] [Version vector collections and embedding
  models](https://github.com/bmwenda/simple-rag/issues/33) so re-embedding
  does not mix incompatible vectors in the active collection.
- [ ] [Add vector-store health checks and recovery
  guidance](https://github.com/bmwenda/simple-rag/issues/34) for failed writes,
  stale versions, and restore operations.
- [ ] [Set the evidence-based migration threshold for a hosted vector
  service](https://github.com/bmwenda/simple-rag/issues/35) if Chroma cannot
  meet availability, scale, or tenancy needs.

Definition of done: operators can deploy, validate, back up, restore, and
re-index the vector store within documented limits.

### P2 — evaluate answer quality and prepare safe operation

- [ ] [Build a versioned retrieval and answer evaluation
  set](https://github.com/bmwenda/simple-rag/issues/43) with expected source
  documents, answers, citations, abstentions, and adversarial or ambiguous
  questions.
- [ ] [Record retrieval, citation, groundedness, abstention, latency, and
  model-cost measurements](https://github.com/bmwenda/simple-rag/issues/44) for
  material retrieval or prompt changes.
- [ ] [Add dependency, secret, and static-security scanning to
  CI](https://github.com/bmwenda/simple-rag/issues/45), with defined severity
  thresholds.
- [ ] [Record sanitized authentication and authorization audit
  events](https://github.com/bmwenda/simple-rag/issues/46) without tokens,
  message content, or other secrets. The single-owner bearer-token check and
  ownership enforcement are already implemented.
- [ ] [Define document retention, deletion, privacy, and incident-response
  policies](https://github.com/bmwenda/simple-rag/issues/48) before accepting
  production documents. Chat/profile immediate hiding and 29-day scheduled
  purge are already implemented.
- [ ] [Set rate limits, request limits, model usage limits, and spend
  alerts](https://github.com/bmwenda/simple-rag/issues/49) before any public
  or multi-user deployment.
- [ ] [Write a deployment and operations
  runbook](https://github.com/bmwenda/simple-rag/issues/50) for configuration,
  migrations, rollback, backups, dead letter queues, vector recovery, and
  incident triage.

Definition of done: answer quality has a repeatable baseline and the product
can be operated securely with explicit limits, recovery procedures, and
privacy commitments.

## Confirmed decisions

- AWS is the supported cloud provider; OpenTofu is the infrastructure-as-code
  tool. Terraform is not used for this project.
- S3 events flow through SQS to Lambda. Direct S3-to-Lambda invocation is
  rejected by the event parser.
- The default document-size limit is 100 MiB and must be enforced at every
  upload and ingestion boundary.
- A document should become searchable within five minutes of upload
  completion.
- The first browser release serves one administratively provisioned owner;
  multi-tenancy is out of scope.
- Deleted chat/profile content becomes inaccessible immediately and is
  physically purged within 30 days. Current scheduled purge age is 29 days.
- Availability and reliability should be cost-aware. Measurable availability,
  recovery-time, recovery-point, and queue-delay targets must be set before
  infrastructure work begins.

## References

- [Chat API contract](chat-api-plan.md)
- [S3 source-bucket ingestion](s3-ingestion.md)
- [Retention scheduler example](../deploy/cron/chat-retention.cron.example)
- [AWS S3 event notifications](https://docs.aws.amazon.com/AmazonS3/latest/userguide/EventNotifications.html)
- [AWS Lambda with SQS](https://docs.aws.amazon.com/lambda/latest/dg/with-sqs.html)
