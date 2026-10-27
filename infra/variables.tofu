variable "aws_region" {
  description = "AWS region in which to provision the ingestion resources."
  type        = string
}

variable "name" {
  description = "Base name used for the ingestion resources."
  type        = string
  default     = "simple-rag-ingestion"

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9-]{1,41}[a-z0-9]$", var.name))
    error_message = "name must contain 3-43 lowercase letters, numbers, or hyphens."
  }
}

variable "source_bucket_name" {
  description = "Globally unique source bucket name; generated when omitted."
  type        = string
  default     = null
  nullable    = true
}

variable "source_prefix" {
  description = "Optional object-key prefix accepted by the ingestion worker."
  type        = string
  default     = "incoming"

  validation {
    condition     = !startswith(var.source_prefix, "/") && !endswith(var.source_prefix, "/")
    error_message = "source_prefix must not start or end with a slash."
  }
}

variable "enable_source_bucket_versioning" {
  description = "Retain prior source-object versions at additional storage cost."
  type        = bool
  default     = false
}

variable "image_digest" {
  description = "ECR image digest to deploy; omit while creating the repository before the first push."
  type        = string
  default     = null
  nullable    = true

  validation {
    condition     = var.image_digest == null ? true : can(regex("^sha256:[0-9a-f]{64}$", var.image_digest))
    error_message = "image_digest must be an ECR sha256 digest."
  }
}

variable "runtime_secret_arn" {
  description = "ARN of an existing Secrets Manager JSON secret with the ingestion runtime credentials."
  type        = string
  default     = null
  nullable    = true

  validation {
    condition     = var.runtime_secret_arn == null ? true : can(regex("^arn:[^:]+:secretsmanager:[^:]+:[0-9]{12}:secret:.+", var.runtime_secret_arn))
    error_message = "runtime_secret_arn must be a Secrets Manager secret ARN."
  }
}

variable "lambda_environment_variables" {
  description = "Non-secret environment variables for the ingestion worker."
  type        = map(string)
  default     = {}

  validation {
    condition = alltrue([
      for name in keys(var.lambda_environment_variables) :
      !contains(["API_BEARER_TOKEN", "DATABASE_URL", "OPENAI_API_KEY", "INGESTION_RUNTIME_SECRET_ARN", "MAX_DOCUMENT_SIZE_BYTES", "S3_SOURCE_BUCKET", "S3_SOURCE_PREFIX"], upper(name))
    ])
    error_message = "Secrets and managed ingestion settings cannot be supplied through lambda_environment_variables."
  }
}

variable "lambda_timeout_seconds" {
  description = "Maximum Lambda execution time in seconds."
  type        = number
  default     = 300

  validation {
    condition     = var.lambda_timeout_seconds >= 1 && var.lambda_timeout_seconds <= 900
    error_message = "lambda_timeout_seconds must be between 1 and 900."
  }
}

variable "lambda_memory_size_mb" {
  description = "Memory allocated to the ingestion worker."
  type        = number
  default     = 2048

  validation {
    condition     = var.lambda_memory_size_mb >= 128 && var.lambda_memory_size_mb <= 10240
    error_message = "lambda_memory_size_mb must be between 128 and 10240."
  }
}

variable "max_document_size_bytes" {
  description = "Largest source object that the ingestion worker accepts."
  type        = number
  default     = 104857600

  validation {
    condition     = var.max_document_size_bytes >= 1
    error_message = "max_document_size_bytes must be positive."
  }
}

variable "queue_visibility_timeout_seconds" {
  description = "Time an in-flight ingestion message remains hidden."
  type        = number
  default     = 1800

  validation {
    condition     = var.queue_visibility_timeout_seconds >= 6 * var.lambda_timeout_seconds
    error_message = "queue visibility must be at least six times the Lambda timeout."
  }
}

variable "batch_size" {
  description = "Maximum SQS records supplied to one Lambda invocation."
  type        = number
  default     = 1

  validation {
    condition     = var.batch_size >= 1 && var.batch_size <= 10
    error_message = "batch_size must be between 1 and 10."
  }
}

variable "queue_message_retention_seconds" {
  description = "Retention period for unprocessed ingestion messages."
  type        = number
  default     = 345600
}

variable "dead_letter_retention_seconds" {
  description = "Retention period for messages moved to the dead-letter queue."
  type        = number
  default     = 1209600
}

variable "max_receive_count" {
  description = "Receives allowed before a message moves to the dead-letter queue."
  type        = number
  default     = 5

  validation {
    condition     = var.max_receive_count >= 1
    error_message = "max_receive_count must be at least 1."
  }
}

variable "log_retention_days" {
  description = "CloudWatch log retention; shorter defaults limit stored log data."
  type        = number
  default     = 7

  validation {
    condition = contains([
      1, 3, 5, 7, 14, 30, 60, 90, 120, 150, 180, 365, 400, 545, 731,
      1096, 1827, 2192, 2557, 2922, 3288, 3653,
    ], var.log_retention_days)
    error_message = "log_retention_days must be a CloudWatch-supported retention period."
  }
}

variable "force_destroy_source_bucket" {
  description = "Allow source-bucket deletion when it still contains objects."
  type        = bool
  default     = false
}

variable "tags" {
  description = "Tags applied to all supported AWS resources."
  type        = map(string)
  default = {
    Application = "simple-rag"
    ManagedBy   = "opentofu"
  }
}
