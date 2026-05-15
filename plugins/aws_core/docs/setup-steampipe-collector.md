# AWS Steampipe Collector Setup

This note is for running the first AWS Core collector slice against a real AWS
account. It assumes the TAP Docker stack is running for this worktree and that
you want the `vpc-subnet-v0` profile: VPCs and subnets only.

## Current Capability

Implemented:

- collector registration: `plugins.aws_core.collectors.steampipe_inventory:steampipe-inventory`
- trusted profile: `vpc-subnet-v0`
- Steampipe CLI subprocess wrapper
- AWS static credential resolution through `tap_cares.secrets`
- redacted run records and logs for config, secret, and Steampipe failures

Still pending:

- VPC/subnet normalization into GRIFT
- GRIFT import from collector output
- deletes/reaping

So the current run proves configuration, credentials, Steampipe execution, and
row collection. It does not yet place VPC/subnet nodes on the grid.

## Host Prerequisites

Install Steampipe and the AWS plugin where the TAP web container can execute
them. The collector currently invokes:

```bash
steampipe query '<trusted sql>' --output json
```

Inside the TAP container, verify:

```bash
scripts/dc exec web steampipe --version
scripts/dc exec web steampipe plugin list
```

If Steampipe is installed only on the host, the container will not see it. Use a
container-visible install or mount/bake the binary into the dev image before a
live collector run.

## AWS Permissions

Use read-only credentials for the target account. For the first profile, the
credentials need enough EC2 read access for VPCs and subnets. Start with the
least-privilege policy you are comfortable debugging, or a managed read-only
policy for a first smoke test.

The collector is read-only against AWS.

## Secret File

Create a secret file under this worktree's `tap_secrets/` directory, or use the
shared `$HOME/tap-secrets/` directory if your session symlinks to it.

Example path:

```text
tap_secrets/aws/legacy-readonly.secret.json
```

Example contents:

```json
{
  "scope": "aws",
  "key": "legacy-readonly",
  "kind": "aws_static_access_key",
  "description": "Read-only AWS credentials for the TAP AWS Steampipe collector.",
  "data": {
    "access_key_id": "AKIA...",
    "secret_access_key": "...",
    "region": "us-east-1"
  },
  "metadata": {
    "account_id": "123456789012"
  }
}
```

Optional: add `data.session_token` for temporary credentials.

Do not commit `*.secret.json` files. The repo ignores them.

After adding or changing secret files, restart the web container so tap-cares
reloads the mounted secrets:

```bash
scripts/dc restart web
```

Confirm startup logs mention loaded secrets or, at minimum, do not report JSON
or duplicate-key errors.

## Collector Setting

The v0 collector reads `AWS_CORE_STEAMPIPE_COLLECTOR`. In local Docker
sessions, put it in `.env.local` as compact JSON so `scripts/dc` passes it into
the web container.

Example `.env.local` entry:

```bash
AWS_CORE_STEAMPIPE_COLLECTOR={"target_key":"legacy","account_id":"123456789012","partition":"aws","secret_ref":{"scope":"aws","key":"legacy-readonly"},"regions":["us-east-1"],"profile":"vpc-subnet-v0"}
```

Equivalent Python shape:

```python
AWS_CORE_STEAMPIPE_COLLECTOR = {
    "target_key": "legacy",
    "account_id": "123456789012",
    "partition": "aws",
    "secret_ref": {"scope": "aws", "key": "legacy-readonly"},
    "regions": ["us-east-1"],
    "profile": "vpc-subnet-v0",
}
```

This setting is non-secret. It stores only `SecretRef` identity.

Restart the web container after changing `.env.local`:

```bash
scripts/dc restart web
```

Keep account IDs and target labels accurate so run records are easy to
interpret later. Until a durable on-grid collector configuration model lands,
this environment-backed setting is the local operator path.

## Smoke Checks

Before using TAP, verify Steampipe can see the account from inside the same
container environment:

```bash
scripts/dc exec web steampipe query 'select vpc_id, region, cidr_block from aws_vpc;' --output json
scripts/dc exec web steampipe query 'select subnet_id, vpc_id, region, cidr_block from aws_vpc_subnet;' --output json
```

If these fail, fix Steampipe installation, AWS plugin installation, credentials,
or permissions before debugging TAP collector code.

## Expected TAP Behavior

Successful current-phase run:

- records `RUN_STARTED`
- resolves and validates the AWS secret
- executes `aws_vpc` and `aws_vpc_subnet` trusted queries
- records `PROFILE_COLLECTED`
- records `RUN_COMPLETED`
- sets a summary like:

```text
Collected AWS legacy vpc-subnet-v0: 3 VPC rows, 12 subnet rows (normalization pending).
```

Common failure buckets:

- `CONFIG_INVALID`: missing or malformed `AWS_CORE_STEAMPIPE_COLLECTOR`; on a
  first run this usually means TAP does not yet know which AWS account or
  secret ref to use, so create the secret file, add the `.env.local` value
  above, and restart `web`
- `SECRET_MISSING_FILE`: `AWS_CORE_STEAMPIPE_COLLECTOR.secret_ref` points at a
  secret that tap-cares did not load from a matching `*.secret.json` file; add
  the named file under `tap_secrets/` and restart `web`
- `SECRET_INVALID`: secret file was loaded, but it has the wrong kind or
  malformed secret data
- `PROFILE_INVALID`: unknown trusted profile
- `STEAMPIPE_FAILED`: missing binary, timeout, non-zero Steampipe exit, or invalid JSON

Credential values must not appear in logs or run records. If they do, stop and
fix redaction before continuing.

## Next Implementation Step

The next phase is to normalize the collected VPC and subnet rows into a GRIFT
batch using the edge vocabulary in `../edges/` and the model contract in
`../models/`. That phase should create/update AWS account, VPC, subnet, region,
and availability-zone relationships through GRIFT rather than direct ORM writes.
