mock_provider "aws" {
  mock_data "aws_iam_policy_document" {
    defaults = {
      json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}"
    }
  }

  mock_resource "aws_s3_bucket" {
    defaults = {
      id  = "simple-rag-test-sources"
      arn = "arn:aws:s3:::simple-rag-test-sources"
    }
  }

  mock_resource "aws_sqs_queue" {
    defaults = {
      arn = "arn:aws:sqs:eu-west-1:123456789012:mock-queue"
      url = "https://sqs.eu-west-1.amazonaws.com/123456789012/mock-queue"
    }
  }

  mock_resource "aws_lambda_function" {
    defaults = {
      arn = "arn:aws:lambda:eu-west-1:123456789012:function:simple-rag-ingestion"
    }
  }

  mock_resource "aws_iam_role" {
    defaults = {
      arn = "arn:aws:iam::123456789012:role/simple-rag-ingestion-role"
    }
  }

  mock_resource "aws_cloudwatch_log_group" {
    defaults = {
      arn = "arn:aws:logs:eu-west-1:123456789012:log-group:/aws/lambda/simple-rag-ingestion"
    }
  }
}

variables {
  aws_region         = "eu-west-1"
  lambda_artifact_key = "simple-rag/ingestion.zip"
  source_bucket_name = "simple-rag-test-sources"
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
    condition = length(aws_s3_bucket_public_access_block.artifact) == 0 ? true : alltrue([
      aws_s3_bucket_public_access_block.artifact[0].block_public_acls,
      aws_s3_bucket_public_access_block.artifact[0].block_public_policy,
      aws_s3_bucket_public_access_block.artifact[0].ignore_public_acls,
      aws_s3_bucket_public_access_block.artifact[0].restrict_public_buckets,
    ])
    error_message = "The managed artifact bucket must block every form of public access."
  }

  assert {
    condition = length(aws_s3_bucket_server_side_encryption_configuration.artifact) == 0 ? true : anytrue([
      for rule in aws_s3_bucket_server_side_encryption_configuration.artifact[0].rule :
      one(rule.apply_server_side_encryption_by_default).sse_algorithm == "AES256"
    ])
    error_message = "The managed artifact bucket must enable server-side encryption."
  }

  assert {
    condition     = length(aws_s3_bucket.artifact) == 0 ? true : aws_lambda_function.ingestion.s3_bucket == aws_s3_bucket.artifact[0].id
    error_message = "Lambda must use the managed artifact bucket by default."
  }

  assert {
    condition     = aws_sqs_queue.ingestion.sqs_managed_sse_enabled && aws_sqs_queue.dead_letter.sqs_managed_sse_enabled
    error_message = "The ingestion queue and dead-letter queue must be encrypted."
  }

  assert {
    condition     = aws_lambda_event_source_mapping.ingestion.event_source_arn == aws_sqs_queue.ingestion.arn
    error_message = "Lambda must consume from SQS rather than directly from S3."
  }

  assert {
    condition     = aws_lambda_function.ingestion.environment[0].variables.S3_SOURCE_BUCKET == aws_s3_bucket.source.id
    error_message = "Lambda must receive the provisioned source bucket name."
  }

  assert {
    condition     = length(aws_s3_bucket_versioning.source) == 0
    error_message = "Source-bucket versioning must be opt-in to avoid default storage growth."
  }

  assert {
    condition     = aws_cloudwatch_log_group.ingestion.retention_in_days == 7
    error_message = "The default log retention must bound stored CloudWatch data."
  }
}

run "reject_application_secrets" {
  command = plan

  variables {
    lambda_environment_variables = {
      OPENAI_API_KEY = "must-not-enter-opentofu-state"
    }
  }

  expect_failures = [var.lambda_environment_variables]
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

run "allow_existing_artifact_bucket" {
  command = plan

  variables {
    lambda_artifact_bucket = "private-deployment-artifacts"
  }

  assert {
    condition     = length(aws_s3_bucket.artifact) == 0
    error_message = "An existing artifact bucket must suppress managed artifact-bucket creation."
  }

  assert {
    condition     = aws_lambda_function.ingestion.s3_bucket == "private-deployment-artifacts"
    error_message = "Lambda must use the explicitly supplied artifact bucket."
  }
}
