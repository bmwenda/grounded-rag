output "source_bucket_name" {
  description = "Name of the private document source bucket."
  value       = aws_s3_bucket.source.id
}

output "source_bucket_arn" {
  description = "ARN of the private document source bucket."
  value       = aws_s3_bucket.source.arn
}

output "lambda_artifact_bucket_name" {
  description = "Name of the managed or supplied bucket containing the Lambda deployment zip."
  value       = local.lambda_artifact_bucket
}

output "ingestion_queue_arn" {
  description = "ARN of the queue consumed by the ingestion Lambda."
  value       = aws_sqs_queue.ingestion.arn
}

output "ingestion_queue_url" {
  description = "URL of the queue consumed by the ingestion Lambda."
  value       = aws_sqs_queue.ingestion.url
}

output "dead_letter_queue_arn" {
  description = "ARN of the ingestion dead-letter queue."
  value       = aws_sqs_queue.dead_letter.arn
}

output "lambda_function_arn" {
  description = "ARN of the ingestion Lambda function."
  value       = aws_lambda_function.ingestion.arn
}

output "lambda_execution_role_arn" {
  description = "ARN of the least-privilege Lambda execution role."
  value       = aws_iam_role.ingestion.arn
}
