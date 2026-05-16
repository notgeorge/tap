# AWS Steampipe Collector Setup

This note is for running the first AWS Core collector slice against a real AWS
account. It assumes the TAP Docker stack is running for this worktree. The v0
scope is **VPCs and subnets only** — a hardcoded collector capability, not
operator-selectable.

The collector is **zero-config**: it discovers everything it needs from a
single well-known secret. There is no Django setting, environment variable, or
config object (`AWS_CORE_STEAMPIPE_COLLECTOR` was removed — putting plugin
config in core infra is an anti-pattern).

## Current Capability

Implemented:

- collector registration: `plugins.aws_core.collectors.steampipe_inventory:steampipe-inventory`
- zero-config secret discovery: one well-known `SecretRef(aws, steampipe-collector)`
- four-check self-test (`AWS_SECRET_PRESENT` / `SECRET_VALID` /
  `STEAMPIPE_AVAILABLE` / `AWS_IDENTITY`) run as collection phase 1
- Steampipe CLI subprocess wrapper, AWS static credential resolution through
  `tap_cares.secrets`, redacted run records and logs

Still pending:

- VPC/subnet normalization into GRIFT (and `PRODUCED_BATCH` linkage)
- GRIFT import from collector output
- deletes/reaping

So the current run proves secret discovery, credentials, Steampipe execution,
and row collection. It does not yet place VPC/subnet nodes on the grid.

## Host Prerequisites

Install Steampipe and the AWS plugin where the TAP web container can execute
them. The collector invokes:

```bash
steampipe query '<trusted sql>' --output json
```

Inside the TAP container, verify:

```bash
scripts/dc exec web steampipe --version
scripts/dc exec web steampipe plugin list
```

If Steampipe is installed only on the host, the container will not see it
(`STEAMPIPE_AVAILABLE` self-test fails with readiness `error`). Use a
container-visible install or bake the binary into the dev image before a live
collector run.

## AWS Permissions

Use read-only credentials for the target account. The v0 scope needs enough
EC2 read access for VPCs and subnets, plus `sts:GetCallerIdentity` /
`aws_caller_identity` for the self-test identity check. Start with a managed
read-only policy for a first smoke test.

The collector is read-only against AWS.

## Secret File

The collector resolves exactly one secret: scope `aws`, key
`steampipe-collector`. Create it under this worktree's `tap_secrets/`
directory (local compose mounts `./tap_secrets` → `/run/tap-secrets`), or the
shared `$HOME/tap-secrets/` directory if your session symlinks to it.

Path (the basename must match the key):

```text
tap_secrets/aws/steampipe-collector.secret.json
```

Contents:

```json
{
  "scope": "aws",
  "key": "steampipe-collector",
  "kind": "aws_static_access_key",
  "description": "Read-only AWS credentials for the TAP AWS Steampipe collector.",
  "data": {
    "access_key_id": "AKIA...",
    "secret_access_key": "...",
    "region": "us-east-1"
  },
  "metadata": {
    "account_id": "123456789012",
    "target_regions": ["us-east-1", "us-west-2"]
  }
}
```

Required:

- `data.region` — the primary collection region and the region used for the
  identity check.
- `metadata.account_id` — the 12-digit AWS account you intend to collect. The
  self-test verifies the live credentials resolve to this account; a mismatch
  is `misconfigured`, not `error`.

Optional:

- `data.session_token` — for temporary credentials.
- `metadata.target_regions` — a list that downscopes collection to those
  regions. Absent ⇒ only `data.region`. This is an interim stopgap until a
  durable collector-configuration object exists; do not treat it as permanent.

Do not commit `*.secret.json` files — the repo ignores them. After adding or
changing the secret, restart the web container so tap-cares reloads it:

```bash
scripts/dc restart web
```

Confirm startup logs mention loaded secrets and do not report JSON or
duplicate-key errors. There is **no** `.env.local` / collector-setting step —
the secret is the entire configuration.

## Smoke Checks

Before using TAP, verify Steampipe can see the account from inside the same
container environment:

```bash
scripts/dc exec web steampipe query 'select account_id, arn from aws_caller_identity;' --output json
scripts/dc exec web steampipe query 'select vpc_id, region, cidr_block from aws_vpc;' --output json
scripts/dc exec web steampipe query 'select subnet_id, vpc_id, region, cidr_block from aws_vpc_subnet;' --output json
```

If these fail, fix Steampipe installation, AWS plugin installation,
credentials, or permissions before debugging TAP collector code.

## Expected TAP Behavior

The self-test runs as collection **phase 1**. A non-runnable result fails the
`CollectionJob` before any Steampipe work (standard collector failure mode),
with the readiness reason in the summary. A healthy run:

- records `RUN_STARTED`
- resolves the well-known secret and validates credentials + region + account
- executes the hardcoded `aws_vpc` / `aws_vpc_subnet` queries
- records `COLLECTED`, then `RUN_COMPLETED`
- sets a summary like:

```text
Collected AWS vpc-subnet-v0 (acct 123456789012): 3 VPC rows, 12 subnet rows (normalization pending).
```

Common failure codes:

- `SECRET_MISSING_FILE`: no `steampipe-collector.secret.json` was loaded; add
  the file under `tap_secrets/aws/` and restart `web`. (Self-test:
  `AWS_SECRET_PRESENT` → `unconfigured`.)
- `SECRET_INVALID`: the secret loaded but is the wrong kind or fails the AWS
  credential schema. (Self-test: `SECRET_VALID` → `misconfigured`.)
- `TARGET_INVALID`: the secret is a valid credential but is missing
  `data.region` or `metadata.account_id`, or `metadata.target_regions` is
  malformed. (Self-test: `SECRET_VALID` → `misconfigured`.)
- `STEAMPIPE_FAILED`: missing binary, timeout, non-zero Steampipe exit, or
  invalid JSON. (Self-test: `STEAMPIPE_AVAILABLE` → `error`.)

Credential values must not appear in logs or run records. If they do, stop and
fix redaction before continuing.

## Next Implementation Step

Normalize the collected VPC and subnet rows into a GRIFT batch using the AWS
edge vocabulary (`HOSTS_VPC`, `PARTITIONED_INTO_SUBNET`, `BELONGS_TO_VPC`,
`BOUND_TO_AZ`, `BELONGS_TO_ACCOUNT`) and the model contract in `../models/`.
That phase creates/updates AWS account, VPC, subnet, region, and
availability-zone relationships through GRIFT (never direct ORM writes), names
each batch, and links it to the run via a `PRODUCED_BATCH` edge.
```
