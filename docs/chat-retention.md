# Chat-history retention

Chat and profile deletion is a two-stage process. The API sets `deleted_at`
and excludes the content from authenticated reads immediately. A separate,
one-shot command physically deletes eligible rows; PostgreSQL foreign-key
cascades remove the associated chats, messages, and citation snapshots in the
same transaction.

Run the command with the same application image and database configuration as
the API:

```bash
uv run --frozen chat-retention
```

The command emits one JSON event to standard output when it succeeds. It emits
a sanitized JSON failure event to standard error and exits nonzero when its
configuration, connection, schema check, or purge fails. It is safe to run
again: already-purged rows are ignored, and each batch commits atomically.

## Configuration

| Variable | Default | Constraint | Purpose |
| --- | ---: | ---: | --- |
| `DATABASE_URL` | required | PostgreSQL URL | Application database containing the migrated chat schema. |
| `CHAT_PURGE_MIN_AGE_DAYS` | `29` | `1` to `29` | Minimum age of `deleted_at` before physical deletion. |
| `CHAT_PURGE_BATCH_SIZE` | `500` | `1` to `10000` | Maximum deleted chats and users removed per transaction. |

The supported schedule runs every six hours. The 29-day minimum leaves four
scheduled opportunities before the 30-day deletion deadline. Do not increase
the minimum or run less frequently if the 30-day upper bound applies.

Apply database migrations before enabling the schedule. The retention
migration adds indexes for both deletion timestamp scans.

## Cron and compatible schedulers

The copyable example at
[`deploy/cron/chat-retention.cron.example`](../deploy/cron/chat-retention.cron.example)
runs at 17 minutes past every sixth hour. Update the absolute checkout and
`uv` paths for the host before installing it with `crontab -e`:

```cron
17 */6 * * * cd /srv/simple-rag && /usr/local/bin/uv run --frozen chat-retention
```

Load `DATABASE_URL` and optional retention settings through the service
environment or the deployment's secret mechanism. Do not place database
credentials in the crontab. Alert on a missing success event or any
`chat_retention_purge_failed` event. A later scheduled run safely retries work
left by a failed invocation.

The same command can be the container command for a Kubernetes CronJob,
Nomad periodic job, systemd timer, or another platform scheduler. Configure the
scheduler to retain logs, surface a nonzero exit status, and avoid disabling
future runs after one failure.

## AWS deployment

Use Amazon EventBridge Scheduler with `rate(6 hours)` and its
[universal AWS SDK target](https://docs.aws.amazon.com/scheduler/latest/UserGuide/managing-targets-universal.html)
to call AWS Batch `SubmitJob` for a job built from the application image. Set
the job command to:

```text
uv run --frozen chat-retention
```

Configure the Batch job definition with at least three
[retry attempts](https://docs.aws.amazon.com/batch/latest/APIReference/API_RetryStrategy.html),
send container logs to CloudWatch Logs, and alert when a job reaches `FAILED`.
Provide `DATABASE_URL` from AWS Secrets Manager or Parameter Store through the
job definition. The scheduler role only needs permission to submit the named
job; the job role should receive only the permissions needed to resolve its
configuration. Database network access should use the same private connectivity
and security-group rules as the API.

EventBridge schedules the work and AWS Batch supplies execution retries. The
application remains portable because neither AWS SDK calls nor scheduler
configuration are part of the purge command.
