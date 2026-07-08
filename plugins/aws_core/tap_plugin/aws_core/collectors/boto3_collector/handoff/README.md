# AWS Core collector — cross-account access handoff

This directory is the operator handoff for pointing the AWS Core collector at a
**running service in an AWS account you do not own** (e.g. a partner's app).
It implements the industry-standard cross-account pattern: the account owner
creates a read-only IAM **role**, and the collector **assumes** it via STS to
get short-lived credentials — no long-lived keys ever cross the boundary.

Spec: `plugins/aws_core/specs/spec-aws-core-secrets.md`
(`req-aws-core-secret-aws-assumed-role`).

Artifacts:

- `cross-account-role.yaml` — CloudFormation template (the default, shortest path).
- `cross-account-role.tf` — Terraform equivalent (only if the partner already uses Terraform).

Both create the **same** role: trust = your collector principal + a required
External ID; permissions = AWS-managed `SecurityAudit` (read-only config, no
data-plane object reads).

A fourth artifact — `collector-principal-policy.json` — is the *operator*-side
policy (yours, not the partner's): it goes on your collector IAM user.

---

## Before you send anything (TAP operator, one-time setup)

1. **Mint a dedicated collector IAM principal** in *your* account — an IAM user
   `tap-aws-core-collector` whose *only* permission is assuming the partner's
   role. Attach the inline policy in **`collector-principal-policy.json`**,
   replacing `<PARTNER_ACCOUNT_ID>` with the partner's account id (add more role
   ARNs to the `Resource` list as you onboard more accounts).

   Its access key becomes the `base` credentials in the secret (below). Because
   it can do nothing but assume a read-only role, a leak is low-value.

2. **Generate an External ID** — any unguessable string, unique per partner.
   Keep it with the secret; you will hand a copy to the partner.

## What you send the partner

- The **collector principal ARN** from step 1 (e.g.
  `arn:aws:iam::111122223333:user/tap-aws-core-collector`).
- The **External ID**.
- One artifact: point them at `cross-account-role.yaml` (or the `.tf`).

## What the partner does (≈1 minute)

**CloudFormation (default):** AWS Console → CloudFormation → Create stack →
upload `cross-account-role.yaml` → paste the **collector principal ARN** and
**External ID** → check *"I acknowledge that this template may create IAM
resources"* → Create. (If you send a pre-filled console launch link, they just
review and click Create.)

**Terraform (if they already use it):** `terraform apply` with
`trustee_principal_arn` and `external_id` set.

Either way they read the read-only grant *before* accepting, and revoke by
deleting the stack / `terraform destroy`.

## What the partner sends back

The stack/apply **Outputs**:

- `RoleArn` → `data.role_arn`
- `AccountId` → `data.expected_account_id`
- plus the **region(s)** the service runs in → `data.region` / `data.regions_allowed`

## Wire it into the collector secret

Drop `boto_collector.secret.json` under `TAP_SECRETS_ROOT` (scope `aws_core`,
key `boto_collector`), kind `aws_assumed_role`:

```json
{
  "scope": "aws_core",
  "key": "boto_collector",
  "kind": "aws_assumed_role",
  "description": "Cross-account read-only role for the partner's running app.",
  "data": {
    "role_arn": "arn:aws:iam::<PARTNER_ACCOUNT_ID>:role/TapAwsCoreCollectorReadOnly",
    "external_id": "<the External ID you generated>",
    "expected_account_id": "<PARTNER_ACCOUNT_ID>",
    "base": {
      "access_key_id": "<collector principal access key>",
      "secret_access_key": "<collector principal secret key>"
    },
    "regions_allowed": ["us-east-1"]
  }
}
```

`manage.py collector selftest` (or the collector's self-test) then proves the
whole chain: it assumes the role, calls `GetCallerIdentity`, and asserts the
landed account equals `expected_account_id`.

> Never commit a real `*.secret.json`. Secret material (base keys, External ID)
> is redacted in all collector logs and errors.
