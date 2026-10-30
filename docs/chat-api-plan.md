# Chat entities and v1 API plan

Status: Design reference; profile, chat lifecycle, message routes, and bounded
retention purge are implemented. Sanitized authentication audit events remain
in the [delivery backlog](specification.md).

This plan defines the first browser chat release for one authenticated user.
It covers profile and chat-history resources, not document upload, document
status, or health endpoints. Those remain in the broader HTTP API backlog.

## Entity model

| Entity | Fields | Relationships and constraints |
| --- | --- | --- |
| Role | Autoincrementing `id`, unique `name` | Seed `owner`. One role has many users; v1 has no role-management API. |
| User | Autoincrementing `id`, required case-normalized unique `email`, optional `first_name` and `last_name`, required `role_id`, `created_at`, `updated_at`, optional `deleted_at` | One user has many chats. The first owner is provisioned outside the API. Authentication-provider fields are deferred. |
| Chat | Autoincrementing `id`, required `user_id` and `title`, `status` (`active` or `archived`), `created_at`, `updated_at`, optional `archived_at` and `deleted_at` | One chat has many messages. The selected chat is UI state, not a persisted status. There is no chat `body` column. |
| ChatMessage | Autoincrementing `id`, required `chat_id`, `speaker` (`user` or `assistant`), `content`, `created_at` | Order by ID within a chat. System prompts are not stored as messages. A failed generation may leave a user message without an assistant reply. |
| ChatCitation | Autoincrementing `id`, required assistant `message_id`, `citation_number`, `document_id`, `index_version`, `chunk_index`, `display_name`, `source_uri`, optional `page_number`, `excerpt` | Citation numbers are unique within an assistant message. Citation metadata is a snapshot, not a foreign key to the document registry, so historical answers survive re-indexing. |

Archive preserves a chat and its history. Deleting a chat or user hides its
content immediately and schedules the user, chats, messages, and citation
snapshots for purge within 30 days; v1 has no restore endpoint. Whether copied
answer content must be redacted after source-document deletion is a separate
production privacy decision. The persistence implementation should use
SQLAlchemy and Alembic, consistent with the document registry.

## HTTP conventions

- All routes use `/v1`, JSON request and response bodies, and
  `Authorization: Bearer <token>`. The first release validates a configured
  `API_BEARER_TOKEN` for the single provisioned owner. There is no public user
  registration endpoint or multi-user identity provider.
- The authenticated user is resolved from the token. Clients never provide
  `user_id` to create or access chats. Resources belonging to another user
  return `404`, the same as nonexistent resources.
- IDs are server-generated integers. Timestamps are UTC ISO 8601 strings.
  Deleted resources are excluded from reads and cannot be modified.
- Lists use opaque `cursor` pagination, default `limit=20`, maximum `100`.
  Responses contain `items` and nullable `next_cursor`.
- Validation errors return `400`, missing or invalid credentials `401`, and
  conflicts `409`. Errors have the shape
  `{ "error": { "code": "...", "message": "..." } }` and never expose backend
  exception details.

## Profile endpoints

| Method and path | Request | Success |
| --- | --- | --- |
| `GET /v1/users/me` | No body | `200` with `id`, `email`, `first_name`, `last_name`, `role` name, and timestamps. |
| `PATCH /v1/users/me` | One or more of `email`, `first_name`, `last_name` | `200` with the updated profile. Duplicate email returns `409`. |
| `DELETE /v1/users/me` | No body | `204`; immediately hides user-owned content and revokes further API access. |

The proposed public `POST /users` and ID-based user deletion are omitted from
v1. The first owner is provisioned administratively, and self-service profile
operations use `/users/me`. Adding more users or administrator endpoints is a
separate product decision.

## Chat and message endpoints

| Method and path | Request | Success |
| --- | --- | --- |
| `POST /v1/chats` | `{ "content": "first question" }` | `201` with `chat`, `user_message`, and `assistant_message`. The server derives a short title from the first question. |
| `GET /v1/chats` | Optional `status=active\|archived`, `cursor`, `limit` | `200` with paginated chat summaries, newest updated first. |
| `GET /v1/chats/{id}` | No body | `200` with chat metadata. |
| `PATCH /v1/chats/{id}` | `title` and/or `status` | `200` with updated chat metadata. Use this to rename, archive, or reactivate a chat. |
| `DELETE /v1/chats/{id}` | No body | `204`; immediately hides the chat and schedules purge. |
| `GET /v1/chats/{id}/messages` | Optional `cursor`, `limit` | `200` with chronological messages, each assistant message including its citation snapshots. |
| `POST /v1/chats/{id}/messages` | `{ "content": "follow-up question" }` | `201` with `user_message` and `assistant_message`. |

`Chat` responses contain `id`, `title`, `status`, `created_at`, `updated_at`,
and nullable `archived_at`; list summaries also expose the latest activity
timestamp. `ChatMessage` responses contain `id`, `speaker`, `content`,
`created_at`, and `citations` (empty for user messages). A citation response
contains `citation_number`, `document_id`, `index_version`, `chunk_index`,
`display_name`, nullable `page_number`, and `excerpt`. Internal foreign keys,
source URIs, and deletion timestamps are not exposed.

Both message-creation routes wait for the answer and persist the user and
assistant messages with the validated citations. A follow-up uses bounded
prior chat history for interpretation but still grounds factual answers in
retrieved documents. Only one answer generation runs at a time per chat.
Archived chats remain readable, but posting to one returns `409` until it is
reactivated. Retrieval or generation failure returns a sanitized `503`; the
user message may already be saved, so the client should reload the chat to
show it without an assistant reply. Clients should not blindly retry a timed-
out creation request because v1 has no idempotency-key contract.

## Implementation status and remaining boundaries

FastAPI handlers, PostgreSQL persistence, SQLAlchemy/Alembic migrations,
configured bearer-token validation, ownership checks, and the profile/chat/
message routes are implemented and covered by tests. The `chat-retention`
command physically purges deleted profiles and chats after 29 days; a sample
six-hour host schedule is in `deploy/cron/chat-retention.cron.example`.

Document upload, status, deletion, and health routes remain outside this
contract and are tracked in issue #36. Authentication outcomes do not yet
produce the sanitized audit events tracked in issue #46. Generated OpenAPI
documentation is not enabled for the production app. Copied answer content
after source-document deletion remains part of the broader privacy decision in
issue #48.

Related backlog: [HTTP API #36](https://github.com/bmwenda/grounded-rag/issues/36),
[chat persistence #40](https://github.com/bmwenda/grounded-rag/issues/40),
[audit events #46](https://github.com/bmwenda/grounded-rag/issues/46), and
[retention #47](https://github.com/bmwenda/grounded-rag/issues/47).
