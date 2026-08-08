# The read-only github-plugins-ro credential store for lanes that git-install private
# plugins (spec-plugin-dependency-resolution.md req-plugin-depres-sources; Decision A/B).
#
# Terraform owns only the SHELL: the named secret + the per-line GetSecretValue grant.
# It DELIBERATELY does not manage the secret VALUE — there is no aws_secretsmanager_secret_
# version resource here, because a Terraform-managed value would be written to
# terraform.tfstate in plaintext (and re-shown on every plan). The value is set out-of-band
# and rotated without a Terraform run:
#
#   aws secretsmanager put-secret-value --secret-id tap-ci/github-plugins-ro \
#     --secret-string '{"token":"ghp_...","host":"github.com","username":"x-access-token"}'
#
# DO NOT add an aws_secretsmanager_secret_version resource — it would fight the out-of-band
# value on every apply and re-leak it into state. The value shape is the github_pat data
# block (tap/plugin_source_auth.py). At runtime a lane resolves it through the secret-source
# seam: a routing manifest names metadata.source = "aws_secrets_manager" + source_ref.
# secret_id = this name, and AwsSecretsManagerSource fetches it via the lane role's AMBIENT
# IAM (the grant below) — no credential is ever stored in GitHub or the workflow.

locals {
  plugin_pull_enabled = var.plugin_pull_secret_name != ""

  # Only lines flagged needs_plugin_pull get to READ the value at runtime (least-privilege).
  # Since 2026-08-08 all TAP plugin repos are public and NO shipped line is flagged — the
  # grant machinery below stays for forks/lines that install private plugins.
  plugin_pull_lines = {
    for name, cfg in var.product_lines : name => cfg
    if local.plugin_pull_enabled && cfg.needs_plugin_pull
  }
}

resource "aws_secretsmanager_secret" "github_plugins_ro" {
  count       = local.plugin_pull_enabled ? 1 : 0
  name        = var.plugin_pull_secret_name
  description = "Read-only github-plugins-ro PAT for CI plugin git-install. VALUE IS SET OUT-OF-BAND via put-secret-value; do NOT add a secret_version resource (would leak into tfstate)."

  # A short recovery window so a torn-down CI secret can be recreated promptly if needed;
  # this holds only a rotatable CI credential, not irreplaceable data.
  recovery_window_in_days = 7
}

# Per-line grant: only needs_plugin_pull lines may read the secret's value at runtime.
data "aws_iam_policy_document" "plugin_pull" {
  count = length(local.plugin_pull_lines) > 0 ? 1 : 0
  statement {
    sid       = "ReadPluginPullPat"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [aws_secretsmanager_secret.github_plugins_ro[0].arn]
  }
}

resource "aws_iam_role_policy" "plugin_pull" {
  for_each = local.plugin_pull_lines
  name     = "plugin-pull"
  role     = aws_iam_role.line[each.key].id
  policy   = data.aws_iam_policy_document.plugin_pull[0].json
}
