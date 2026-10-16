locals {
  lambda_artifact_bucket = var.lambda_artifact_bucket == null ? aws_s3_bucket.artifact[0].id : var.lambda_artifact_bucket
  source_object_arn      = var.source_prefix == "" ? "${aws_s3_bucket.source.arn}/*" : "${aws_s3_bucket.source.arn}/${var.source_prefix}/*"
  source_prefixes        = var.source_prefix == "" ? ["*"] : [var.source_prefix, "${var.source_prefix}/*"]
}

resource "aws_s3_bucket" "artifact" {
  count = var.lambda_artifact_bucket == null ? 1 : 0

  bucket        = var.artifact_bucket_name
  bucket_prefix = var.artifact_bucket_name == null ? "${var.name}-artifacts-" : null
}

resource "aws_s3_bucket_public_access_block" "artifact" {
  count = length(aws_s3_bucket.artifact)

  bucket = aws_s3_bucket.artifact[0].id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "artifact" {
  count = length(aws_s3_bucket.artifact)

  bucket = aws_s3_bucket.artifact[0].id

  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "artifact" {
  count = length(aws_s3_bucket.artifact)

  bucket = aws_s3_bucket.artifact[0].id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_object" "lambda_artifact" {
  count = var.lambda_artifact_local_path == null ? 0 : 1

  bucket = local.lambda_artifact_bucket
  key    = var.lambda_artifact_key
  source = var.lambda_artifact_local_path
  etag   = filemd5(var.lambda_artifact_local_path)

  depends_on = [
    aws_s3_bucket_public_access_block.artifact,
    aws_s3_bucket_ownership_controls.artifact,
    aws_s3_bucket_server_side_encryption_configuration.artifact,
  ]
}

resource "aws_s3_bucket" "source" {
  bucket        = var.source_bucket_name
  bucket_prefix = var.source_bucket_name == null ? "${var.name}-" : null
  force_destroy = var.force_destroy_source_bucket
}

resource "aws_s3_bucket_public_access_block" "source" {
  bucket = aws_s3_bucket.source.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "source" {
  bucket = aws_s3_bucket.source.id

  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "source" {
  bucket = aws_s3_bucket.source.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_versioning" "source" {
  count = var.enable_source_bucket_versioning ? 1 : 0

  bucket = aws_s3_bucket.source.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_sqs_queue" "dead_letter" {
  name                      = "${var.name}-dlq"
  message_retention_seconds = var.dead_letter_retention_seconds
  sqs_managed_sse_enabled   = true
}

resource "aws_sqs_queue" "ingestion" {
  name                       = "${var.name}-queue"
  message_retention_seconds  = var.queue_message_retention_seconds
  visibility_timeout_seconds = var.queue_visibility_timeout_seconds
  sqs_managed_sse_enabled    = true
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dead_letter.arn
    maxReceiveCount     = var.max_receive_count
  })
}

resource "aws_sqs_queue_redrive_allow_policy" "dead_letter" {
  queue_url = aws_sqs_queue.dead_letter.id
  redrive_allow_policy = jsonencode({
    redrivePermission = "byQueue"
    sourceQueueArns   = [aws_sqs_queue.ingestion.arn]
  })
}

data "aws_iam_policy_document" "lambda_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "ingestion" {
  name               = "${var.name}-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
}

resource "aws_cloudwatch_log_group" "ingestion" {
  name              = "/aws/lambda/${var.name}"
  retention_in_days = var.log_retention_days
}

data "aws_iam_policy_document" "ingestion" {
  statement {
    sid    = "ReadSourceObjects"
    effect = "Allow"
    actions = [
      "s3:GetObject",
    ]
    resources = [local.source_object_arn]
  }

  statement {
    sid       = "ListSourcePrefix"
    effect    = "Allow"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.source.arn]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = local.source_prefixes
    }
  }

  statement {
    sid    = "ConsumeIngestionQueue"
    effect = "Allow"
    actions = [
      "sqs:ChangeMessageVisibility",
      "sqs:DeleteMessage",
      "sqs:GetQueueAttributes",
      "sqs:ReceiveMessage",
    ]
    resources = [aws_sqs_queue.ingestion.arn]
  }

  statement {
    sid    = "WriteFunctionLogs"
    effect = "Allow"
    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = ["${aws_cloudwatch_log_group.ingestion.arn}:*"]
  }
}

resource "aws_iam_role_policy" "ingestion" {
  name   = "${var.name}-policy"
  role   = aws_iam_role.ingestion.id
  policy = data.aws_iam_policy_document.ingestion.json
}

resource "aws_lambda_function" "ingestion" {
  function_name = var.name
  description   = "Ingest S3 documents delivered through SQS"
  role          = aws_iam_role.ingestion.arn
  handler       = "src.s3_ingestion_handler.lambda_handler"
  runtime       = "python3.12"
  architectures = ["x86_64"]

  s3_bucket         = local.lambda_artifact_bucket
  s3_key            = var.lambda_artifact_key
  s3_object_version = var.lambda_artifact_version
  layers            = var.lambda_layers

  memory_size = var.lambda_memory_size_mb
  timeout     = var.lambda_timeout_seconds

  environment {
    variables = merge(
      var.lambda_environment_variables,
      {
        MAX_DOCUMENT_SIZE_BYTES = tostring(var.max_document_size_bytes)
        S3_SOURCE_BUCKET        = aws_s3_bucket.source.id
        S3_SOURCE_PREFIX        = var.source_prefix
      },
    )
  }

  depends_on = [
    aws_cloudwatch_log_group.ingestion,
    aws_iam_role_policy.ingestion,
    aws_s3_object.lambda_artifact,
  ]
}

resource "aws_lambda_event_source_mapping" "ingestion" {
  event_source_arn = aws_sqs_queue.ingestion.arn
  function_name    = aws_lambda_function.ingestion.arn
  batch_size       = var.batch_size
  enabled          = true

  depends_on = [aws_iam_role_policy.ingestion]
}
