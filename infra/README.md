# AWS ingestion infrastructure

This root module uses OpenTofu to provision the baseline AWS resources for the
S3-to-SQS-to-Lambda ingestion path:

- a private, encrypted S3 source bucket with opt-in versioning;
- a private, encrypted S3 deployment-artifact bucket by default;
- an encrypted SQS ingestion queue and encrypted dead-letter queue;
- the ingestion Lambda function and its SQS event-source mapping;
- a dedicated execution role limited to the source prefix, ingestion queue,
  and function log group.

The module deliberately does not create an S3 notification or grant S3
permission to publish to the queue. Notification filters and the queue policy
are tracked in issue #17. There is no Lambda resource policy permitting direct
S3 invocation.

## Prerequisites

- OpenTofu 1.9 or newer;
- AWS credentials supplied through the standard AWS credential chain;
- a Lambda-compatible deployment zip, either available locally for OpenTofu to
  upload or already stored in a private S3 artifact bucket;
- application secrets delivered through a runtime secrets integration rather
  than committed files or OpenTofu-managed environment variables.

The deployment artifact must contain the application and its runtime
dependencies, with `src.s3_ingestion_handler.lambda_handler` available as the
handler. By default, the module creates the artifact bucket in `aws_region`,
which keeps it colocated with the Lambda function. Supply
`lambda_artifact_bucket` only to use an existing private bucket in that same
Region. The object key remains configurable so environment-specific locations
are not embedded in this repository.

## Cost defaults

The defaults favor AWS Free Tier-eligible, on-demand services and avoid
resources with fixed recurring charges:

- S3 uses S3-managed encryption rather than a customer-managed KMS key, and
  both created buckets block public access. Source-bucket versioning is opt-in
  so old object versions do not consume storage by default.
- Both standard SQS queues use SQS-managed encryption rather than a billable
  customer-managed KMS key. Queues have no provisioned capacity.
- Lambda uses on-demand execution without provisioned concurrency. Its default
  1,024 MB memory allocation is configurable and should be lowered only after
  confirming the document parser still meets its memory and latency targets.
- CloudWatch Logs retention defaults to seven days to bound stored log data.
- IAM roles and policies have no additional charge.

These settings do not guarantee a zero bill. S3 storage and requests, SQS
requests, Lambda requests and duration, CloudWatch log ingestion and storage,
and data transfer remain usage-based. Free allowances and promotional credits
depend on account eligibility, account age, Region, and aggregate account
usage. Review the current [AWS Free Tier](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/free-tier.html),
[S3 pricing](https://aws.amazon.com/s3/pricing/),
[SQS pricing](https://aws.amazon.com/sqs/pricing/),
[Lambda pricing](https://aws.amazon.com/lambda/pricing/), and
[CloudWatch pricing](https://aws.amazon.com/cloudwatch/pricing/) before apply.

## Validate and test

```bash
tofu -chdir=infra init
tofu -chdir=infra fmt -check
tofu -chdir=infra validate
tofu -chdir=infra test
```

The OpenTofu test uses a mocked AWS provider. It verifies the plan without AWS
credentials or resource creation, including public-access blocks, encryption,
the SQS event source, and rejection of known application-secret inputs.

## Plan and apply

Copy `deployment.auto.tfvars.example` to an ignored local file ending in
`.auto.tfvars`, such as `local.auto.tfvars`, and set
`lambda_artifact_local_path` to the deployment ZIP. OpenTofu creates a private
artifact bucket in `aws_region`, uploads that ZIP, and creates Lambda from the
uploaded object in one apply. OpenTofu loads `.auto.tfvars` files
automatically, so no particular local filename or `-var-file` flag is required.
Keep credentials and application secrets out of tfvars and state. To use a
differently named file, pass it explicitly with `-var-file=path/to/values.tfvars`.

Create the ZIP before planning or applying:

```bash
uv run build-lambda-package
```

The command writes `dist/ingestion.zip`, installs the locked production
dependencies for Python 3.12 Linux x86_64, and includes the `src/` package. It
rejects archives over Lambda's 250 MiB uncompressed ZIP limit; use the
container-image deployment tracked in issue #83 if that happens.

To keep the deployment ZIP in an existing bucket, set
`lambda_artifact_bucket` and `lambda_artifact_key` instead. The bucket must be
in `aws_region`; Lambda cannot load a ZIP from another Region. In that mode,
upload the ZIP before applying. Do not switch `aws_region` for an already
partially applied stack without first reviewing `tofu state list` and the plan.

```bash
tofu -chdir=infra init
tofu -chdir=infra plan -out=deployment.tfplan
tofu -chdir=infra apply deployment.tfplan
```

OpenTofu state can contain infrastructure identifiers and should be stored in
an access-controlled remote backend before shared or production deployment.
Backend selection is environment-specific and intentionally not embedded in
this module.
