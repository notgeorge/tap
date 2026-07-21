# TAP per-product-line CI on AWS CodeBuild GitHub Actions runners.
# spec-dev-validation.md req-dev-validation-product-line-lanes.
#
# One CodeBuild project per product line (boot profile). Each project registers as a
# GitHub Actions self-hosted runner (webhook on WORKFLOW_JOB_QUEUED) and runs that
# line's lane from .github/workflows/product-lines.yml. EC2-mode + privileged so the
# compose stack (docker-in-docker) runs; in-account IAM role gives the lane native
# Bedrock / aws_core capability (the reason to be in AWS, not a speed lever).

terraform {
  # >= 1.10 for the S3 backend's NATIVE locking (use_lockfile) — no DynamoDB table.
  required_version = ">= 1.10"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.60"
    }
  }

  # State lives in S3, NOT on a developer's disk. This is not a preference — a local
  # state file is session-bound, and this module's state was already lost once when the
  # worktree that held it was despawned, leaving the CI infra live-but-unmanaged. The
  # recovery was a full `terraform import` of all 16 resources.
  #
  # The bucket is deliberately NOT managed by this module (chicken-and-egg: the backend
  # must exist before `init`). It is bootstrap infra, created out-of-band and tagged
  # ManagedBy=manual-bootstrap. To recreate it:
  #
  #   aws s3api create-bucket --bucket tap-ci-tfstate --region us-east-1
  #   aws s3api put-public-access-block --bucket tap-ci-tfstate \
  #     --public-access-block-configuration BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
  #   aws s3api put-bucket-versioning --bucket tap-ci-tfstate --versioning-configuration Status=Enabled
  #   aws s3api put-bucket-encryption --bucket tap-ci-tfstate --server-side-encryption-configuration \
  #     '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"},"BucketKeyEnabled":true}]}'
  #   # + a bucket policy denying aws:SecureTransport=false (see README).
  #
  # Versioning is the recovery path for a corrupted/truncated state write; encryption
  # matters because state holds resource metadata (ARNs, policy documents). No SECRET
  # VALUE is in state by design — see secrets.tf on why there is no secret_version
  # resource.
  backend "s3" {
    bucket       = "tap-ci-tfstate"
    key          = "codebuild-runners/terraform.tfstate"
    region       = "us-east-1"
    encrypt      = true
    use_lockfile = true
  }
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
