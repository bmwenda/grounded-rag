# AWS ingestion infrastructure

This root module uses OpenTofu to provision the AWS resources for the
S3-to-SQS-to-Lambda ingestion path:

- a private, encrypted S3 source bucket with opt-in versioning;
- an encrypted SQS ingestion queue and encrypted dead-letter queue;
- object-created notifications for supported lowercase document suffixes under
  the configured source prefix, with a bucket- and account-scoped SQS policy;
- a private ECR repository with immutable tags, basic scanning on push,
  service-managed encryption, and expiry of untagged images after 14 days;
- a dedicated Lambda execution role limited to the source prefix, ingestion
  queue, function log group, and optional runtime secret; and
- a Python 3.12 container-image Lambda and its SQS event-source mapping when
  `image_digest` is configured.

The function uses an ECR image digest. The first apply creates the repository;
after pushing an image, a second apply creates the function from its digest.
When `runtime_secret_arn` is omitted, the SQS mapping is created disabled.

The source prefix must be nonempty. Notifications cover only keys beneath that
prefix, so worker outputs must be written outside it to avoid recursive events.
S3 suffix filters are case-sensitive: uppercase extensions do not trigger a
notification even though the worker's validator accepts them. Keep the suffix
list in `main.tofu` aligned with `src/document_types.py`. There is no Lambda
resource policy permitting direct S3 invocation.

## Prerequisites

- OpenTofu 1.9 or newer;
- Docker with Buildx and AWS CLI v2 for image build and push;
- AWS credentials supplied through the standard AWS credential chain;
- an existing Secrets Manager JSON secret containing `OPENAI_API_KEY`,
  `OPENAI_MODEL`, and `DATABASE_URL` before enabling ingestion.

The secret must be in the selected Region. The handler fetches it at invocation
time using the Lambda execution role. Its ARN, but not its contents, is passed
through OpenTofu. Supply a reachable PostgreSQL database with the pgvector
migration applied before processing real documents; this module does not
provision the database.

## Cost defaults

The defaults favor AWS Free Tier-eligible, on-demand services and avoid
resources with fixed recurring charges:

- S3 uses S3-managed encryption rather than a customer-managed KMS key, and
  the created source bucket blocks public access. Source-bucket versioning is
  opt-in so old object versions do not consume storage by default.
- Both standard SQS queues use SQS-managed encryption rather than a billable
  customer-managed KMS key. Queues have no provisioned capacity.
- ECR uses service-managed encryption and basic scanning. Untagged image
  layers are removed after 14 days; tagged releases remain available for
  rollbacks until explicitly removed.
- Lambda uses on-demand execution without provisioned concurrency. Memory
  defaults to 2,048 MB and must be benchmarked for the parser workload.
- CloudWatch Logs retention defaults to seven days to bound stored log data.
- IAM roles and policies have no additional charge.

These settings do not guarantee a zero bill. S3 storage and requests, SQS
requests, ECR storage and transfer, Lambda requests and duration, Secrets
Manager usage, CloudWatch log ingestion and storage, and data transfer remain
usage-based. Free allowances and promotional credits depend on account
eligibility, account age, Region, and aggregate account usage. Review the
current [AWS Free Tier](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/free-tier.html),
[S3 pricing](https://aws.amazon.com/s3/pricing/),
[SQS pricing](https://aws.amazon.com/sqs/pricing/),
[ECR pricing](https://aws.amazon.com/ecr/pricing/),
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
the ECR configuration, notification rules, queue policy, and the digest-pinned
Lambda mapping. The GitHub
Actions image job builds the Linux x86_64 image and imports the handler and
CPU PyTorch without AWS credentials.

## Plan and apply

Copy `deployment.auto.tfvars.example` to an ignored local file ending in
`.auto.tfvars`, such as `local.auto.tfvars`, and set `aws_region`. OpenTofu loads
these files automatically. Keep credentials and secret contents out of tfvars
and state. The first apply creates the ECR repository and baseline resources.

```bash
tofu -chdir=infra init
tofu -chdir=infra plan -out=deployment.tfplan
tofu -chdir=infra apply deployment.tfplan
```

Build a single-architecture Lambda image from the locked production
dependencies. The Linux x86_64 resolution uses CPU-only PyTorch, and
`Dockerfile.lambda.dockerignore` excludes local documents, credentials, and
generated data.

```bash
docker buildx build --file Dockerfile.lambda --platform linux/amd64 --provenance=false --load \
  --tag simple-rag-ingestion:local .
```

Authenticate and push with an immutable tag such as the Git commit ID. Set
`AWS_REGION` to the value of `aws_region` in the tfvars file:

```bash
REPOSITORY_URL=$(tofu -chdir=infra output -raw ecr_repository_url)
AWS_REGION=eu-west-1
IMAGE_TAG=$(git rev-parse --short=12 HEAD)
aws ecr get-login-password --region "$AWS_REGION" |
  docker login --username AWS --password-stdin "${REPOSITORY_URL%%/*}"
docker tag simple-rag-ingestion:local "$REPOSITORY_URL:$IMAGE_TAG"
docker push "$REPOSITORY_URL:$IMAGE_TAG"
aws ecr describe-images --region "$AWS_REGION" \
  --repository-name "${REPOSITORY_URL#*/}" --image-ids imageTag="$IMAGE_TAG" \
  --query 'imageDetails[0].imageDigest' --output text
```

Copy the reported `sha256:` digest into `image_digest` in the ignored tfvars
file. Set `runtime_secret_arn` to the ARN of the prepared secret, then plan and
apply again. The ECR pull policy allows only the named Lambda function to read
this repository's image layers. OpenTofu will enable the SQS mapping when the
secret ARN is present. The source-bucket notification publishes matching object
creation events to the ingestion queue after the scoped queue policy is in
place. Existing bucket notifications, if any, must be imported or reconciled
before apply because S3 has one notification configuration per bucket.

To roll back, set `image_digest` to the earlier release's ECR digest and apply
again. Keep that image tagged in ECR: Lambda periodically retrieves its image,
so deleting a deployed or rollback digest can break the function. To remove a
failed deployment, clear `image_digest` and apply, which removes the Lambda
and its mapping while retaining the repository and queues. Review the plan
before applying changes to an existing deployment.

OpenTofu state can contain infrastructure identifiers and should be stored in
an access-controlled remote backend before shared or production deployment.
Backend selection is environment-specific and intentionally not embedded in
this module.
