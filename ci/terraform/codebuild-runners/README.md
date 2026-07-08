# TAP per-product-line CI runners (AWS CodeBuild)

Terraform for the per-product-line CI lanes (spec-dev-validation.md
`req-dev-validation-product-line-lanes`). Each product line (a boot profile) gets one
AWS CodeBuild project that registers as a **GitHub Actions self-hosted runner**. The
lane itself lives in `.github/workflows/product-lines.yml`; this module provisions the
compute + identity it runs on.

## Why CodeBuild (not an EC2 fleet, not a SaaS runner)

Managed AWS service (no AMI/NAT/autoscaler to own), EC2-mode compute supports
docker-in-docker (our compose stack needs it), and it runs **in our account** — so the
lane carries an IAM role for native Bedrock / `aws_core` STS testing (the capability
axis; no long-lived creds in GitHub secrets). Full evaluation:
`docs/misc/doc-dev-validation-ci-runner-strategy.md`.

## What it creates

- A CodeConnections **GitHub connection** (unless you supply an existing one).
- Per product line: a **CodeBuild project** (EC2-mode, privileged), a **webhook** on
  `WORKFLOW_JOB_QUEUED`, a **CloudWatch log group**, and a **per-line IAM role**
  (base: logs + connection + reports; capability: Bedrock, optional `aws_core` STS).

## Apply

Prereqs: Terraform ≥ 1.6, AWS creds for the **aws_core account** (us-east-1), `aws` CLI.

```bash
cd ci/terraform/codebuild-runners
cp terraform.tfvars.example terraform.tfvars   # edit as needed
terraform init
terraform apply
```

### The one interactive step (unavoidable)

CodeConnections requires a human to authorize the GitHub App once:

1. First `apply` with `codeconnection_arn = ""` creates the connection **PENDING**.
2. AWS console → **Developer Tools → Settings → Connections** → select
   `tap-ci-github` → **Update pending connection** → install/authorize the AWS
   Connector for GitHub on `notgeorge/tap`.
3. (Optional) paste the now-authorized ARN into `terraform.tfvars` as
   `codeconnection_arn` so future applies reuse it explicitly.

Until authorized, projects exist but builds cannot fetch the repo.

## Wire the workflow

`terraform output runner_labels` prints the exact `runs-on` label per line. They match
`.github/workflows/product-lines.yml` (`codebuild-tap-ci-<line>-…`) as long as
`name_prefix` stays `tap-ci` and the `product_lines` keys match the workflow matrix.
**Adding a line = add a `product_lines` entry here AND a matrix entry in the workflow.**

## Scope down before real use

- Replace `Bedrock` / `sts` `resources = ["*"]` with specific model / role ARNs.
- Consider an S3 state backend (commented in `versions.tf`).
- Add a budget alarm (out of scope of this module).

## Caveats (first draft — validate on apply)

- The `source.auth { type = "CODECONNECTIONS" }` wiring can vary by AWS provider
  version. The load-bearing requirement is an **authorized** CodeConnections GitHub
  connection in the account; if the provider rejects the inline `auth`, drop it.
- Confirm the chosen `codebuild_image` ships Docker + `docker compose` v2.
