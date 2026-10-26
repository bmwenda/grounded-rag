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

variable "queue_visibility_timeout_seconds" {
  description = "Time an in-flight ingestion message remains hidden."
  type        = number
  default     = 1800

  validation {
    condition     = var.queue_visibility_timeout_seconds >= 1
    error_message = "queue_visibility_timeout_seconds must be positive."
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
