# Per-line IAM role. Each product line gets its own role so capability grants can
# diverge per line (least-privilege) — samsite need not hold what a customer line does.

data "aws_iam_policy_document" "assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["codebuild.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "line" {
  for_each           = var.product_lines
  name               = "${var.name_prefix}-${each.key}-role"
  assume_role_policy = data.aws_iam_policy_document.assume.json
}

# Base: logs, use of the GitHub connection, and CodeBuild test/coverage reporting.
data "aws_iam_policy_document" "base" {
  statement {
    sid       = "Logs"
    actions   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["arn:aws:logs:*:*:log-group:/codebuild/${var.name_prefix}-*", "arn:aws:logs:*:*:log-group:/codebuild/${var.name_prefix}-*:*"]
  }
  statement {
    sid       = "UseGitHubConnection"
    actions   = ["codeconnections:GetConnectionToken", "codeconnections:GetConnection", "codeconnections:UseConnection"]
    resources = [local.connection_arn]
  }
  statement {
    sid       = "Reports"
    actions   = ["codebuild:CreateReportGroup", "codebuild:CreateReport", "codebuild:UpdateReport", "codebuild:BatchPutTestCases", "codebuild:BatchPutCodeCoverages"]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "base" {
  for_each = var.product_lines
  name     = "base"
  role     = aws_iam_role.line[each.key].id
  policy   = data.aws_iam_policy_document.base.json
}

# Capability: the AWS-native reason to be here — native Bedrock + optional aws_core STS.
# At least one grant must be enabled or the policy is empty (invalid); bedrock_enabled
# defaults true. Scope resources down (specific model ARNs / role ARNs) as lines firm up.
data "aws_iam_policy_document" "capability" {
  dynamic "statement" {
    for_each = var.bedrock_enabled ? [1] : []
    content {
      sid       = "Bedrock"
      actions   = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream", "bedrock:ListFoundationModels", "bedrock:GetFoundationModel"]
      resources = ["*"]
    }
  }
  dynamic "statement" {
    for_each = length(var.sts_assume_role_arns) > 0 ? [1] : []
    content {
      sid       = "AssumeAwsCoreTestRoles"
      actions   = ["sts:AssumeRole"]
      resources = var.sts_assume_role_arns
    }
  }
}

resource "aws_iam_role_policy" "capability" {
  # Only attach when there is at least one capability grant.
  for_each = (var.bedrock_enabled || length(var.sts_assume_role_arns) > 0) ? var.product_lines : {}
  name     = "capability"
  role     = aws_iam_role.line[each.key].id
  policy   = data.aws_iam_policy_document.capability.json
}
