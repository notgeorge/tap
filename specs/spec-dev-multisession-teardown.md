# Multi-Session Dev Environment — Teardown

## Philosophy

Every spawned dev session must despawn cleanly with **one command**. Manual teardown is error-prone — leftover containers, orphaned volumes, dangling networks, abandoned worktrees, and unmerged session branches accumulate fast and silently degrade the developer experience. A single-invocation teardown script is the public interface; everything else is implementation detail.

This spec lives separately from [spec-dev-multisession.md](spec-dev-multisession.md) so the teardown feature can be tracked, reviewed, and shipped on its own cadence.

## Goals

|   |   |  |
| :---: | --- | --- |
| 1. | Single Command | One invocation removes the entire session — no follow-up cleanup required. |
| 2. | Total Cleanup | Containers, networks, volumes, worktree, and session branch are all gone. |
| 3. | Safety Rails | Refuse to destroy uncommitted work or unmerged branches without explicit consent. |
| 4. | Idempotent | Running teardown on an already-torn-down session is a no-op with a clear message, not an error. |

## Requirements

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-dev-multisession-teardown-script | [Despawn Script](#despawn-script) | Proposed | The one-line public interface |
| req-dev-multisession-teardown-cleanup | [Total Cleanup](#total-cleanup) | Proposed | What "torn down" means |
| req-dev-multisession-teardown-safety | [Safety Rails](#safety-rails) | Proposed | Don't lose uncommitted work |

### Despawn Script
----
RID: `req-dev-multisession-teardown-script`
Status: `Proposed`

The public interface is a single command:

```bash
scripts/despawn-session.sh <name>
```

Where `<name>` matches a session previously spawned via the procedure in [spec-dev-multisession.md](spec-dev-multisession.md) (e.g. `cli`, `vscode`).

Optional flags (each off by default):

- `--force` — skip the safety check for uncommitted changes in the session worktree.
- `--keep-branch` — leave the `session/<name>` git branch in place (useful when work has been pushed and is awaiting PR merge).
- `--dry-run` — print what would be removed, take no destructive action.

#### Implementation

The script lives at `scripts/despawn-session.sh` and is checked into the repo. It runs from anywhere (uses `git rev-parse --show-toplevel` of the primary checkout for relative ops).

Sequence:

1. Resolve session: read `~/tap-sessions/<name>/.env.local` to recover `COMPOSE_PROJECT_NAME`. If the worktree or env file is missing, exit 0 with a "nothing to do" message (idempotent).
2. Safety check (skipped under `--force`): `git -C ~/tap-sessions/<name> status --porcelain` must be empty. If not, refuse and print the dirty paths.
3. Stop the stack: `cd ~/tap-sessions/<name> && scripts/dc down -v --remove-orphans`.
4. Remove the worktree: `git worktree remove ~/tap-sessions/<name>` (use `--force` if step 2 was bypassed).
5. Delete the branch (skipped under `--keep-branch`): `git branch -D session/<name>`.
6. Print a confirmation summary listing what was removed.

Under `--dry-run`, steps 3–5 are reported but not executed.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-dev-multisession-teardown-script-1 | Single-command invocation | Proposed | `scripts/despawn-session.sh <name>` is the only command needed for a clean teardown. | |
| req-dev-multisession-teardown-script-2 | Idempotent | Proposed | Running on a non-existent or already-torn-down session exits 0 with no error. | |
| req-dev-multisession-teardown-script-3 | Dry run | Proposed | `--dry-run` reports planned actions without executing them. | |

### Total Cleanup
----
RID: `req-dev-multisession-teardown-cleanup`
Status: `Proposed`

After a successful (non-dry-run, non-`--keep-branch`) teardown for session `<name>`, none of the following may exist:

- Containers in project `tap_<name>`.
- Networks owned by project `tap_<name>`.
- Volumes owned by project `tap_<name>` (notably `tap_<name>_postgres_data`).
- The worktree directory `~/tap-sessions/<name>`.
- The git branch `session/<name>`.

#### Verification

Run from the primary checkout:

```bash
docker ps -a --filter "label=com.docker.compose.project=tap_<name>"   # no rows
docker volume ls --format '{{.Name}}' | grep "^tap_<name>_"           # no output
docker network ls --filter "name=tap_<name>_" --format '{{.Name}}'    # no rows
[[ -d ~/tap-sessions/<name> ]] && echo FAIL || echo OK                # OK
git branch --list "session/<name>" | grep .                           # no output
```

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-dev-multisession-teardown-cleanup-1 | No containers | Proposed | No containers remain in the session's compose project. | |
| req-dev-multisession-teardown-cleanup-2 | No volumes | Proposed | No volumes remain in the session's compose project. | |
| req-dev-multisession-teardown-cleanup-3 | No network | Proposed | No networks remain in the session's compose project. | |
| req-dev-multisession-teardown-cleanup-4 | Worktree removed | Proposed | The `~/tap-sessions/<name>` directory is gone. | |
| req-dev-multisession-teardown-cleanup-5 | Branch removed | Proposed | The `session/<name>` branch is gone (unless `--keep-branch`). | |

### Safety Rails
----
RID: `req-dev-multisession-teardown-safety`
Status: `Proposed`

Teardown is destructive. The script must refuse to proceed when it could lose work:

- If `git status` in the worktree shows uncommitted or untracked files, abort and print a list of dirty paths. Override with `--force`.
- If the `session/<name>` branch has commits not present on `main` (or its upstream tracking branch), abort and require `--force` to drop them. The script should mention that pushing the branch first is the safer path.
- If a stack-up step fails partway through teardown, the script must report which steps did and did not run, so the developer can finish manually.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-dev-multisession-teardown-safety-1 | Dirty worktree blocks | Proposed | Teardown aborts with a clear error when the worktree has uncommitted changes, unless `--force`. | |
| req-dev-multisession-teardown-safety-2 | Unmerged commits block | Proposed | Teardown aborts when `session/<name>` has commits not on `main`, unless `--force`. | |
| req-dev-multisession-teardown-safety-3 | Partial-failure transparency | Proposed | A mid-teardown failure prints which steps succeeded and which remain. | |

## Manual Teardown (until the script lands)

Until `scripts/despawn-session.sh` is implemented, follow this sequence by hand for session `<name>`:

```bash
cd ~/tap-sessions/<name>
git status                                        # confirm clean
scripts/dc down -v --remove-orphans
cd ~/Documents/code/tap
git worktree remove ~/tap-sessions/<name>
git branch -D session/<name>
```

Verify with the commands in [Total Cleanup → Verification](#verification).

## Status Vocabulary

Standard TAP states: `Proposed`, `Approved for Development`, `In Development`, `Implemented`, `Verified`, `Refactoring`, `Deprecating`, `Deprecated`.
