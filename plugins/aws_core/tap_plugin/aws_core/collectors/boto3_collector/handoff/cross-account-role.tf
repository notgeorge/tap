# TAP AWS Core collector — cross-account, read-only access role (Terraform).
#
# Equivalent to cross-account-role.yaml. Use this ONLY if you already manage
# this AWS account with Terraform; otherwise the CloudFormation template is the
# shorter path. Apply in the TARGET account (the one running the service TAP
# will observe).
#
# What you are granting: one IAM role that the TAP collector principal may
# ASSUME (no long-lived key), gated by an External ID, granted AWS-managed
# SecurityAudit (read-only config/metadata; no data-plane object reads).
# Revoke by `terraform destroy` on this role.

variable "trustee_principal_arn" {
  description = "Exact IAM principal ARN of the TAP collector allowed to assume this role (supplied by the TAP operator)."
  type        = string
}

variable "external_id" {
  description = "Shared External ID supplied by the TAP operator; required on every AssumeRole. Do not invent your own."
  type        = string
  sensitive   = true
}

variable "role_name" {
  description = "Name for the created IAM role."
  type        = string
  default     = "TapAwsCoreCollectorReadOnly"
}

variable "max_session_duration_seconds" {
  description = "Longest lifetime of a single assumed session (900..43200)."
  type        = number
  default     = 3600
}

data "aws_caller_identity" "current" {}

data "aws_iam_policy_document" "trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "AWS"
      identifiers = [var.trustee_principal_arn]
    }

    condition {
      test     = "StringEquals"
      variable = "sts:ExternalId"
      values   = [var.external_id]
    }
  }
}

resource "aws_iam_role" "collector" {
  name                 = var.role_name
  description          = "Read-only cross-account access for the TAP AWS Core collector."
  max_session_duration = var.max_session_duration_seconds
  assume_role_policy   = data.aws_iam_policy_document.trust.json

  tags = {
    managed-by = "tap-aws-core"
    purpose    = "cross-account-read-only-collector"
  }
}

resource "aws_iam_role_policy_attachment" "security_audit" {
  role = aws_iam_role.collector.name
  # Read-only configuration/metadata. To also allow data-plane reads, attach
  # arn:aws:iam::aws:policy/ReadOnlyAccess as well — only if asked.
  policy_arn = "arn:aws:iam::aws:policy/SecurityAudit"
}

output "role_arn" {
  description = "Send this back to the TAP operator -> data.role_arn."
  value       = aws_iam_role.collector.arn
}

output "account_id" {
  description = "Send this back too -> data.expected_account_id."
  value       = data.aws_caller_identity.current.account_id
}
