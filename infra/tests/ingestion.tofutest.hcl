mock_provider "aws" {
  mock_data "aws_iam_policy_document" {
    defaults = {
      json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}"
    }
  }

  mock_resource "aws_s3_bucket" {
    defaults = {
      id  = "grounded-rag-test-sources"
      arn = "arn:aws:s3:::grounded-rag-test-sources"
    }
  }

  mock_resource "aws_sqs_queue" {
    defaults = {
      arn = "arn:aws:sqs:eu-west-1:123456789012:mock-queue"
      url = "https://sqs.eu-west-1.amazonaws.com/123456789012/mock-queue"
    }
  }

  mock_resource "aws_iam_role" {
    defaults = {
      arn = "arn:aws:iam::123456789012:role/grounded-rag-ingestion-role"
    }
  }

  mock_data "aws_partition" {
    defaults = {
      partition = "aws"
    }
  }

  mock_data "aws_caller_identity" {
    defaults = {
      account_id = "123456789012"
    }
  }

  mock_resource "aws_ecr_repository" {
    defaults = {
      repository_url = "123456789012.dkr.ecr.eu-west-1.amazonaws.com/grounded-rag-ingestion"
    }
  }

  mock_resource "aws_lambda_function" {
    defaults = {
      arn = "arn:aws:lambda:eu-west-1:123456789012:function:grounded-rag-ingestion"
    }
  }

  mock_resource "aws_cloudwatch_log_group" {
    defaults = {
      arn = "arn:aws:logs:eu-west-1:123456789012:log-group:/aws/lambda/grounded-rag-ingestion"
    }
  }
}

variables {
  aws_region         = "eu-west-1"
  source_bucket_name = "grounded-rag-test-sources"
}

run "secure_ingestion_plan" {
  command = plan

  assert {
    condition = alltrue([
      aws_s3_bucket_public_access_block.source.block_public_acls,
      aws_s3_bucket_public_access_block.source.block_public_policy,
      aws_s3_bucket_public_access_block.source.ignore_public_acls,
      aws_s3_bucket_public_access_block.source.restrict_public_buckets,
    ])
    error_message = "The source bucket must block every form of public access."
  }

  assert {
    condition = anytrue([
      for rule in aws_s3_bucket_server_side_encryption_configuration.source.rule :
      one(rule.apply_server_side_encryption_by_default).sse_algorithm == "AES256"
    ])
    error_message = "The source bucket must enable server-side encryption."
  }

  assert {
    condition     = aws_sqs_queue.ingestion.sqs_managed_sse_enabled && aws_sqs_queue.dead_letter.sqs_managed_sse_enabled
    error_message = "The ingestion queue and dead-letter queue must be encrypted."
  }

  assert {
    condition     = length(aws_s3_bucket_versioning.source) == 0
    error_message = "Source-bucket versioning must be opt-in to avoid default storage growth."
  }

  assert {
    condition     = aws_cloudwatch_log_group.ingestion.retention_in_days == 7
    error_message = "The default log retention must bound stored CloudWatch data."
  }

  assert {
    condition     = length(aws_lambda_function.ingestion) == 0 && length(aws_lambda_event_source_mapping.ingestion) == 0
    error_message = "The first apply must create ECR without requiring an image that has not been pushed."
  }

  assert {
    condition     = aws_ecr_repository.ingestion.image_tag_mutability == "IMMUTABLE" && aws_ecr_repository.ingestion.image_scanning_configuration[0].scan_on_push
    error_message = "ECR must use immutable tags and scan on push."
  }

  assert {
    condition     = aws_ecr_repository.ingestion.encryption_configuration[0].encryption_type == "AES256"
    error_message = "The ECR repository must use service-managed encryption."
  }

  assert {
    condition     = jsondecode(aws_ecr_lifecycle_policy.ingestion.policy).rules[0].selection.tagStatus == "untagged"
    error_message = "The lifecycle policy must expire stale untagged images."
  }

  assert {
    condition = length(aws_s3_bucket_notification.source.queue) == 17 && alltrue([
      for rule in aws_s3_bucket_notification.source.queue :
      rule.filter_prefix == "incoming/" && contains(local.supported_document_suffixes, rule.filter_suffix)
    ])
    error_message = "Only supported source documents must notify the ingestion queue."
  }

  assert {
    condition = alltrue([
      for rule in aws_s3_bucket_notification.source.queue :
      rule.queue_arn == aws_sqs_queue.ingestion.arn && contains(rule.events, "s3:ObjectCreated:*")
    ])
    error_message = "Every supported source event must target the ingestion queue."
  }

  assert {
    condition = alltrue([
      jsondecode(aws_sqs_queue_policy.ingestion.policy).Statement[0].Action == "sqs:SendMessage",
      jsondecode(aws_sqs_queue_policy.ingestion.policy).Statement[0].Resource == aws_sqs_queue.ingestion.arn,
      jsondecode(aws_sqs_queue_policy.ingestion.policy).Statement[0].Principal.Service == "s3.amazonaws.com",
      jsondecode(aws_sqs_queue_policy.ingestion.policy).Statement[0].Condition.ArnEquals["aws:SourceArn"] == aws_s3_bucket.source.arn,
      jsondecode(aws_sqs_queue_policy.ingestion.policy).Statement[0].Condition.StringEquals["aws:SourceAccount"] == "123456789012",
    ])
    error_message = "Only the configured S3 source may publish to the ingestion queue."
  }
}

run "reject_bucket_wide_notifications" {
  command = plan

  variables {
    source_prefix = ""
  }

  expect_failures = [var.source_prefix]
}

run "deploy_image_digest" {
  command = plan

  variables {
    image_digest       = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    runtime_secret_arn = "arn:aws:secretsmanager:eu-west-1:123456789012:secret:ingestion-test"
  }

  assert {
    condition     = aws_lambda_function.ingestion[0].package_type == "Image" && endswith(aws_lambda_function.ingestion[0].image_uri, "@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
    error_message = "Lambda must deploy the selected immutable ECR digest."
  }

  assert {
    condition     = aws_lambda_event_source_mapping.ingestion[0].event_source_arn == aws_sqs_queue.ingestion.arn && aws_lambda_event_source_mapping.ingestion[0].enabled
    error_message = "The configured worker must consume the ingestion queue."
  }

  assert {
    condition     = jsondecode(aws_ecr_repository_policy.ingestion.policy).Statement[0].Condition.ArnEquals["aws:SourceArn"] == "arn:aws:lambda:eu-west-1:123456789012:function:grounded-rag-ingestion"
    error_message = "ECR pull permissions must be scoped to the ingestion function."
  }
}

run "reject_invalid_digest" {
  command = plan

  variables {
    image_digest = "latest"
  }

  expect_failures = [var.image_digest]
}

run "hold_mapping_without_secret" {
  command = plan

  variables {
    image_digest = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
  }

  assert {
    condition     = !aws_lambda_event_source_mapping.ingestion[0].enabled
    error_message = "The ingestion mapping must remain disabled until runtime credentials are configured."
  }
}

run "allow_opt_in_versioning" {
  command = plan

  variables {
    enable_source_bucket_versioning = true
  }

  assert {
    condition     = aws_s3_bucket_versioning.source[0].versioning_configuration[0].status == "Enabled"
    error_message = "Source-bucket versioning must be available as an explicit opt-in."
  }
}
