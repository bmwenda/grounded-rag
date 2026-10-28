locals {
  # Keep this list aligned with src/document_types.py. S3 suffix filters are
  # case-sensitive; the worker remains the final document-type validator.
  supported_document_suffixes = toset([
    ".csv", ".docx", ".epub", ".html", ".htm", ".json", ".md",
    ".odt", ".pdf", ".pptx", ".rtf", ".rst", ".tsv", ".txt",
    ".xml", ".yaml", ".yml",
  ])
  source_object_arn = "${aws_s3_bucket.source.arn}/${var.source_prefix}/*"
  source_prefixes   = [var.source_prefix, "${var.source_prefix}/*"]
  function_arn      = "arn:${data.aws_partition.current.partition}:lambda:${var.aws_region}:${data.aws_caller_identity.current.account_id}:function:${var.name}"
}

data "aws_partition" "current" {}

data "aws_caller_identity" "current" {}

resource "aws_ecr_repository" "ingestion" {
  name                 = var.name
  image_tag_mutability = "IMMUTABLE"

  encryption_configuration {
    encryption_type = "AES256"
  }

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_lifecycle_policy" "ingestion" {
  repository = aws_ecr_repository.ingestion.name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Expire untagged images after 14 days"
      selection = {
        tagStatus   = "untagged"
        countType   = "sinceImagePushed"
        countUnit   = "days"
        countNumber = 14
      }
      action = { type = "expire" }
    }]
  })
}

resource "aws_ecr_repository_policy" "ingestion" {
  repository = aws_ecr_repository.ingestion.name
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid    = "LambdaECRImageRetrievalPolicy"
      Effect = "Allow"
      Principal = {
        Service = "lambda.amazonaws.com"
      }
      Action = ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer"]
      Condition = {
        StringEquals = {
          "aws:SourceAccount" = data.aws_caller_identity.current.account_id
        }
        ArnEquals = {
          "aws:SourceArn" = local.function_arn
        }
      }
    }]
  })
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

resource "aws_sqs_queue_policy" "ingestion" {
  queue_url = aws_sqs_queue.ingestion.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid      = "AllowSourceBucketNotifications"
      Effect   = "Allow"
      Action   = "sqs:SendMessage"
      Resource = aws_sqs_queue.ingestion.arn
      Principal = {
        Service = "s3.amazonaws.com"
      }
      Condition = {
        ArnEquals = {
          "aws:SourceArn" = aws_s3_bucket.source.arn
        }
        StringEquals = {
          "aws:SourceAccount" = data.aws_caller_identity.current.account_id
        }
      }
    }]
  })
}

resource "aws_s3_bucket_notification" "source" {
  bucket = aws_s3_bucket.source.id

  dynamic "queue" {
    for_each = local.supported_document_suffixes
    content {
      id            = "source-${trimprefix(queue.value, ".")}"
      queue_arn     = aws_sqs_queue.ingestion.arn
      events        = ["s3:ObjectCreated:*"]
      filter_prefix = "${var.source_prefix}/"
      filter_suffix = queue.value
    }
  }

  depends_on = [aws_sqs_queue_policy.ingestion]
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

  dynamic "statement" {
    for_each = var.runtime_secret_arn == null ? [] : [var.runtime_secret_arn]
    content {
      sid       = "ReadRuntimeSecret"
      effect    = "Allow"
      actions   = ["secretsmanager:GetSecretValue"]
      resources = [statement.value]
    }
  }
}

resource "aws_iam_role_policy" "ingestion" {
  name   = "${var.name}-policy"
  role   = aws_iam_role.ingestion.id
  policy = data.aws_iam_policy_document.ingestion.json
}

resource "aws_lambda_function" "ingestion" {
  count         = var.image_digest == null ? 0 : 1
  function_name = var.name
  description   = "Ingest S3 documents delivered through SQS"
  role          = aws_iam_role.ingestion.arn
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.ingestion.repository_url}@${var.image_digest}"
  architectures = ["x86_64"]
  memory_size   = var.lambda_memory_size_mb
  timeout       = var.lambda_timeout_seconds

  environment {
    variables = merge(var.lambda_environment_variables, {
      MAX_DOCUMENT_SIZE_BYTES = tostring(var.max_document_size_bytes)
      S3_SOURCE_BUCKET        = aws_s3_bucket.source.id
      S3_SOURCE_PREFIX        = var.source_prefix
      }, var.runtime_secret_arn == null ? {} : {
      INGESTION_RUNTIME_SECRET_ARN = var.runtime_secret_arn
    })
  }

  depends_on = [
    aws_cloudwatch_log_group.ingestion,
    aws_iam_role_policy.ingestion,
    aws_ecr_repository_policy.ingestion,
  ]
}

resource "aws_lambda_event_source_mapping" "ingestion" {
  count            = var.image_digest == null ? 0 : 1
  event_source_arn = aws_sqs_queue.ingestion.arn
  function_name    = aws_lambda_function.ingestion[0].arn
  batch_size       = var.batch_size
  enabled          = var.runtime_secret_arn != null

  depends_on = [aws_iam_role_policy.ingestion]
}
