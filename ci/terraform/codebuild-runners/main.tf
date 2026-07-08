locals {
  # Use the provided connection, else the one Terraform creates (needs manual auth).
  connection_arn = var.codeconnection_arn != "" ? var.codeconnection_arn : aws_codeconnections_connection.github[0].arn
}

# GitHub connection (CodeConnections / GitHub App). Created PENDING; authorize once in
# the console. Skipped when codeconnection_arn is supplied (reuse an existing one).
resource "aws_codeconnections_connection" "github" {
  count         = var.codeconnection_arn == "" ? 1 : 0
  name          = "${var.name_prefix}-github"
  provider_type = "GitHub"
}

resource "aws_cloudwatch_log_group" "line" {
  for_each          = var.product_lines
  name              = "/codebuild/${var.name_prefix}-${each.key}"
  retention_in_days = var.log_retention_days
}

# One CodeBuild project per product line, acting as a GitHub Actions runner.
resource "aws_codebuild_project" "line" {
  for_each      = var.product_lines
  name          = "${var.name_prefix}-${each.key}"
  description   = "TAP per-product-line CI: ${each.key} (boot profile ${each.value.profile})"
  service_role  = aws_iam_role.line[each.key].arn
  build_timeout = var.build_timeout_minutes

  artifacts {
    type = "NO_ARTIFACTS"
  }

  environment {
    type                        = "LINUX_CONTAINER"
    compute_type                = each.value.compute_type
    image                       = var.codebuild_image
    image_pull_credentials_type = "CODEBUILD"
    privileged_mode             = true # docker-in-docker for the compose stack
  }

  source {
    type            = "GITHUB"
    location        = "https://github.com/${var.github_owner}/${var.github_repo}.git"
    git_clone_depth = 1

    # In GHA-runner mode the workflow's steps run on the runner CodeBuild provisions;
    # this buildspec is a placeholder and is not what defines the lane (that lives in
    # .github/workflows/product-lines.yml).
    buildspec = "version: 0.2\nphases:\n  build:\n    commands:\n      - echo \"GHA runner\""

    # GitHub auth via the CodeConnections app. NOTE: exact wiring can vary by AWS
    # provider version; the load-bearing requirement is an AUTHORIZED CodeConnections
    # GitHub connection in the account (see README). If your provider rejects `auth`
    # here, remove it — an authorized connection for the provider is used implicitly.
    auth {
      type     = "CODECONNECTIONS"
      resource = local.connection_arn
    }
  }

  logs_config {
    cloudwatch_logs {
      group_name = aws_cloudwatch_log_group.line[each.key].name
    }
  }
}

# Webhook that starts a build to service each queued GitHub Actions job for this repo.
resource "aws_codebuild_webhook" "line" {
  for_each     = var.product_lines
  project_name = aws_codebuild_project.line[each.key].name
  build_type   = "BUILD"

  filter_group {
    filter {
      type    = "EVENT"
      pattern = "WORKFLOW_JOB_QUEUED"
    }
  }
}
