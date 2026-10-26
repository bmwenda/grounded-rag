# AWS ingestion infrastructure

This root module uses OpenTofu to provision the baseline AWS resources for the
S3-to-SQS ingestion path:

- a private, encrypted S3 source bucket with opt-in versioning;
- an encrypted SQS ingestion queue and encrypted dead-letter queue;
- a dedicated Lambda execution role limited to the source prefix, ingestion
  queue, and function log group; and
- the ingestion function's CloudWatch log group.

Issue #83 adds the ECR image, ingestion Lambda function, and SQS event-source
mapping. The ZIP deployment workflow is intentionally not supported.

The module deliberately does not create an S3 notification or grant S3
permission to publish to the queue. Notification filters and the queue policy
are tracked in issue #17. There is no Lambda resource policy permitting direct
S3 invocation.

## Prerequisites

- OpenTofu 1.9 or newer;
- AWS credentials supplied through the standard AWS credential chain;
- application secrets delivered through a runtime secrets integration rather
  than committed files or OpenTofu-managed environment variables.

## Cost defaults

The defaults favor AWS Free Tier-eligible, on-demand services and avoid
resources with fixed recurring charges:

- S3 uses S3-managed encryption rather than a customer-managed KMS key, and
  the created source bucket blocks public access. Source-bucket versioning is
  opt-in so old object versions do not consume storage by default.
- Both standard SQS queues use SQS-managed encryption rather than a billable
  customer-managed KMS key. Queues have no provisioned capacity.
- CloudWatch Logs retention defaults to seven days to bound stored log data.
- IAM roles and policies have no additional charge.

These settings do not guarantee a zero bill. S3 storage and requests, SQS
requests, CloudWatch log ingestion and storage, and data transfer remain
usage-based. Free allowances and promotional credits depend on account
eligibility, account age, Region, and aggregate account usage. Review the
current [AWS Free Tier](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/free-tier.html),
[S3 pricing](https://aws.amazon.com/s3/pricing/),
[SQS pricing](https://aws.amazon.com/sqs/pricing/), and
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
and the queue configuration. The image-based Lambda resources are tested in
issue #83.

## Plan and apply

Copy `deployment.auto.tfvars.example` to an ignored local file ending in
`.auto.tfvars`, such as `local.auto.tfvars`, and set the values required for
the source bucket. OpenTofu loads `.auto.tfvars` files automatically, so no
particular local filename or `-var-file` flag is required. Keep credentials
and application secrets out of tfvars and state. To use a differently named
file, pass it explicitly with `-var-file=path/to/values.tfvars`.

Issue #83 will document the ECR image build, push, digest selection, and
deployment steps. Do not deploy a Lambda ZIP for this workload.

```bash
tofu -chdir=infra init
tofu -chdir=infra plan -out=deployment.tfplan
tofu -chdir=infra apply deployment.tfplan
```

OpenTofu state can contain infrastructure identifiers and should be stored in
an access-controlled remote backend before shared or production deployment.
Backend selection is environment-specific and intentionally not embedded in
this module.
