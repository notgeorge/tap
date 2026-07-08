output "codeconnection_arn" {
  description = "The GitHub CodeConnections ARN in use."
  value       = local.connection_arn
}

output "codeconnection_action_required" {
  description = "Whether the connection still needs manual authorization."
  value = var.codeconnection_arn == "" ? (
    "ACTION REQUIRED: authorize the new connection in AWS console (Developer Tools > Settings > Connections) — it is PENDING until then."
  ) : "Using a pre-existing connection (assumed already authorized)."
}

output "codebuild_project_names" {
  description = "Project name per product line."
  value       = { for k, p in aws_codebuild_project.line : k => p.name }
}

output "runner_labels" {
  description = "The runs-on label to use in the workflow, per product line."
  # $$ escapes to $ so the literal GitHub expression survives Terraform rendering.
  value = { for k, p in aws_codebuild_project.line : k => "codebuild-${p.name}-$${{ github.run_id }}-$${{ github.run_attempt }}" }
}

output "line_role_arns" {
  description = "Per-line IAM role ARNs (attach further least-privilege grants here)."
  value       = { for k, r in aws_iam_role.line : k => r.arn }
}
