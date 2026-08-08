variable "aws_region" {
  description = "Region for the CodeBuild CI (us-east-1 for widest Bedrock coverage)."
  type        = string
  default     = "us-east-1"
}

variable "github_owner" {
  description = "GitHub owner of the repo CodeBuild connects to."
  type        = string
  default     = "unified-systems-com"
}

variable "github_repo" {
  description = "GitHub repo name."
  type        = string
  default     = "tap"
}

variable "name_prefix" {
  description = "Prefix for all created resources (projects: <prefix>-<line>)."
  type        = string
  default     = "tap-ci"
}

variable "codeconnection_arn" {
  description = <<-EOT
    ARN of an EXISTING, already-authorized CodeConnections GitHub connection.
    Leave empty ("") to have Terraform create one — it comes up PENDING and must be
    authorized once in the AWS console (Developer Tools > Settings > Connections)
    before any build can run. This is the one unavoidable interactive step.
  EOT
  type        = string
  default     = ""
}

variable "product_lines" {
  description = <<-EOT
    Map of product line -> config. The key is the line name and part of the project
    name (<prefix>-<line>) and the runner label. `profile` is the tap_boot profile the
    lane boots. Add a line here to add a lane (also add a matrix entry in the workflow).
  EOT
  type = map(object({
    profile      = string
    compute_type = optional(string, "BUILD_GENERAL1_LARGE") # 8 vCPU / 15 GB
    # Lines that git-install PRIVATE plugins need the read-only github-plugins-ro PAT
    # (resolved from Secrets Manager via the source seam). Since 2026-08-08 every TAP
    # plugin repo is public, so no shipped lane needs it — the flag stays as the
    # mechanism for forks/lines that install private plugins (a flagged line gets
    # GetSecretValue on the plugin-pull secret; nothing else changes).
    needs_plugin_pull = optional(bool, false)
  }))
  default = {
    test_all = { profile = "test_all", needs_plugin_pull = false } # union superset lane; public repos, anonymous clone
    samsite  = { profile = "samsite", needs_plugin_pull = false }  # fedramp demo line; public repos, anonymous clone
  }
}

variable "plugin_pull_secret_name" {
  description = <<-EOT
    Name of the AWS Secrets Manager secret holding the read-only github-plugins-ro PAT that
    lanes use to git-install private plugins. Terraform creates only the SHELL (the named
    secret + each needing-line's GetSecretValue grant) and NEVER the value — a Terraform-
    managed value would land in terraform.tfstate in plaintext. Populate it out-of-band:
      aws secretsmanager put-secret-value --secret-id <this> \
        --secret-string '{"token":"ghp_...","host":"github.com","username":"x-access-token"}'
    Empty ("") disables the secret + grants (a monorepo-only deployment needs neither).
  EOT
  type        = string
  default     = "tap-ci/github-plugins-ro"
}

variable "codebuild_image" {
  description = "CodeBuild EC2-mode image (must include Docker for the compose stack)."
  type        = string
  default     = "aws/codebuild/amazonlinux-x86_64-standard:5.0"
}

variable "build_timeout_minutes" {
  type    = number
  default = 40
}

variable "log_retention_days" {
  type    = number
  default = 30
}

# --- Capability axis (the AWS-native reason to run CI here) -------------------
variable "bedrock_enabled" {
  description = "Grant the lane role bedrock:InvokeModel* for native tap_ai / LLM tests."
  type        = bool
  # Default OFF (flipped 2026-08-08): nothing in the current lanes invokes Bedrock, and an
  # unused wildcard grant on a runner that executes approved fork-PR code is exactly the
  # standing power the security posture says not to carry. Re-enable WITH specific model
  # ARNs (scope resources in iam.tf at the same time) when a lane actually needs it —
  # over-restriction relaxes cheaply.
  default = false
}

variable "sts_assume_role_arns" {
  description = <<-EOT
    Role ARNs the lane may sts:AssumeRole for aws_core cross-account testing.
    Empty = no AssumeRole granted. Fill with the test-target role ARNs (reuse the
    External-ID discipline from plugins/aws_core/.../handoff/cross-account-role.yaml).
  EOT
  type        = list(string)
  default     = []
}
