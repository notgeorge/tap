# TAP per-product-line CI on AWS CodeBuild GitHub Actions runners.
# spec-dev-validation.md req-dev-validation-product-line-lanes.
#
# One CodeBuild project per product line (boot profile). Each project registers as a
# GitHub Actions self-hosted runner (webhook on WORKFLOW_JOB_QUEUED) and runs that
# line's lane from .github/workflows/product-lines.yml. EC2-mode + privileged so the
# compose stack (docker-in-docker) runs; in-account IAM role gives the lane native
# Bedrock / aws_core capability (the reason to be in AWS, not a speed lever).

terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.60"
    }
  }
  # Recommended: an S3 backend in the aws_core account. Left local by default so a
  # first apply works without pre-provisioning state infra. Uncomment + fill in.
  # backend "s3" {
  #   bucket = "tap-ci-tfstate"
  #   key    = "codebuild-runners/terraform.tfstate"
  #   region = "us-east-1"
  # }
}

provider "aws" {
  region = var.aws_region
  # Credentials come from the environment / a named profile (aws_core account).
  default_tags {
    tags = {
      Project   = "tap-ci"
      ManagedBy = "terraform"
      Component = "product-line-runners"
    }
  }
}
