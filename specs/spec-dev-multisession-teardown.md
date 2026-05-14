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
| req-dev-multisession-teardown-script | [Despawn Script](#despawn-script) | Implemented | The one-line public interface |
| req-dev-multisession-teardown-cleanup | [Total Cleanup](#total-cleanup) | Implemented | What "torn down" means |
| req-dev-multisession-teardown-safety | [Safety Rails](#safety-rails) | Deprecated | Replaced by aggressive-by-default with confirm prompt |

### Despawn Script
----
RID: `req-dev-multisession-teardown-script`
Status: `Implemented`

The public interface is a single command:

```bash
scripts/despawn-session.sh <name>            # interactive confirm
scripts/despawn-session.sh <name> --yes      # skip confirm
scripts/despawn-session.sh                   # interactive — pick from registry
scripts/despawn-session.sh <name> --purge-image  # also force-rebuild image
```

Where `<name>` matches a session previously spawned via the procedure in [spec-dev-multisession.md](spec-dev-multisession.md) (e.g. `cli`, `vscode`). The script also accepts names that are not in the registry — useful for cleaning up half-spawned sessions where the registry append never happened.

Flags:

- `--yes` / `-y` — skip the confirmation prompt. Pair with the named form for one-line invocation in scripts.
- `--purge-image` — also remove the per-project web image (`tap_<name>-web`) so the next spawn rebuilds without using Docker image cache. Runtime Python state lives in compose volumes and is removed by normal despawn volume cleanup.

#### Behavior

Best-effort, aggressive teardown. Individual cleanup-step failures log a warning and continue rather than aborting — the goal is "leave nothing behind," not "halt at the first surprise." Re-running on an already-torn-down session is safe (each step's no-op path is reached cleanly).

#### Implementation

The script lives at `scripts/despawn-session.sh` and is checked into the repo. It runs from anywhere (uses `git rev-parse --show-toplevel` of the primary checkout for relative ops).

Sequence:

1. **Pick the session.** If `<name>` is provided, use it. Otherwise display the registry and prompt. Names not in the registry are accepted (cleaning up a half-spawned session may not have a registry row).
2. **Show the plan and confirm.** Lists what will be removed (containers, volumes, networks, worktree path including all uncommitted files, branch, registry row, optionally the per-project image). Skip with `--yes`.
3. **Stop the stack.** Prefer `cd <worktree> && scripts/dc down -v --remove-orphans` so `.env.local` resolves the project name correctly. Fall back to `docker compose -p tap_<name> down -v --remove-orphans` if the worktree is unavailable.
4. **Belt-and-suspenders volume / network cleanup.** Even after step 3, named volumes / networks under `tap_<name>_` are matched and removed explicitly. This catches the failure mode where a previous `dc down` couldn't identify the project (missing `.env.local`).
5. **Remove the worktree and branch.** `git worktree remove --force` followed by `git branch -D session/<name>`. If the worktree directory survives somehow (e.g. removed outside git's awareness), `rm -rf` it.
6. **Remove the registry row.** `sed -i.bak "/^<name> /d" ~/tap-sessions/.registry`, freeing the band for reuse. See [req-dev-multisession-port-registry](spec-dev-multisession.md#per-machine-session-registry).
7. **(Optional) Purge the per-project image** with `--purge-image`: `docker rmi` for any image matching `tap_<name>-web`. Forces a no-cache rebuild on the next spawn. Runtime Python state is not image-owned; `down -v` and the residual volume cleanup remove the Postgres data, container venv, and uv cache volumes.
8. **Print a verification block** with the commands the operator can run to confirm everything's gone.

#### Best-effort semantics

Individual cleanup steps log a warning on failure and continue. The script doesn't run with `set -e`. The reasoning: when an operator invokes despawn, what they want is "leave nothing behind from this session." Aborting on the first surprise (a missing volume, a worktree git no longer knows about, etc.) leaves more partial state than just pushing through. Re-running on an already-clean session is safe — each step's no-op branch is reached without error.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-dev-multisession-teardown-script-1 | Single-command invocation | Proposed | `scripts/despawn-session.sh <name>` is the only command needed for a clean teardown. | |
| req-dev-multisession-teardown-script-2 | Idempotent | Proposed | Running on a non-existent or already-torn-down session exits 0 with no error. | |
| req-dev-multisession-teardown-script-3 | Image purge flag | Proposed | `--purge-image` removes the per-project web image so the next spawn rebuilds without cache. | |
| req-dev-multisession-teardown-script-4 | Half-spawn recovery | Proposed | Despawn cleans up sessions whose registry append never happened (worktree exists, registry row doesn't). | |
| req-dev-multisession-teardown-script-5 | Best-effort cleanup | Proposed | Individual cleanup-step failures log a warning and continue. | |

### Total Cleanup
----
RID: `req-dev-multisession-teardown-cleanup`
Status: `Proposed`

After a successful (non-dry-run, non-`--keep-branch`) teardown for session `<name>`, none of the following may exist:

- Containers in project `tap_<name>`.
- Networks owned by project `tap_<name>`.
- Volumes owned by project `tap_<name>` (notably `tap_<name>_postgres_data`, `tap_<name>_venv`, and `tap_<name>_uv_cache`).
- The worktree directory `~/tap-sessions/<name>`.
- The git branch `session/<name>`.
- The session's row in `~/tap-sessions/.registry` (band must be freed for reuse).

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
| req-dev-multisession-teardown-cleanup-2 | No volumes | Proposed | No volumes remain in the session's compose project, including Postgres data, the container Python virtualenv, and uv cache. | |
| req-dev-multisession-teardown-cleanup-3 | No network | Proposed | No networks remain in the session's compose project. | |
| req-dev-multisession-teardown-cleanup-4 | Worktree removed | Proposed | The `~/tap-sessions/<name>` directory is gone. | |
| req-dev-multisession-teardown-cleanup-5 | Branch removed | Proposed | The `session/<name>` branch is gone (unless `--keep-branch`). | |
| req-dev-multisession-teardown-cleanup-6 | Registry row removed | Proposed | The session's row in `~/tap-sessions/.registry` is gone, freeing its band for reuse. | |

### Safety Rails
----
RID: `req-dev-multisession-teardown-safety`
Status: `Deprecated`

#### Status Details
Deprecated 2026-04-27. The original safety design called for despawn to refuse on dirty worktrees and unmerged commits, with `--force` as an opt-in override. In practice, despawn is most often invoked exactly when state is dirty (mid-debugging, after a failed spawn, after a SIGKILL during migrate) — making the safety rails the rule and `--force` the path everyone takes. We replaced this with a confirm prompt (`--yes` to skip) and aggressive-by-default cleanup. The interactive confirm is the safety mechanism; the spec's explicit dirty-worktree refusal is no longer the way.

If sticky safety is needed for a workflow (e.g. a CI job that must never destroy unpushed work), the right shape is a separate `--safe` flag that re-introduces the dirty checks, rather than making safety the default.

The original ACIDs below are preserved for history but should not be implemented under their original framing.

#### Acceptance Criteria (historical)

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-dev-multisession-teardown-safety-1 | Dirty worktree blocks | Deprecated | Original framing — replaced by confirm prompt. | |
| req-dev-multisession-teardown-safety-2 | Unmerged commits block | Deprecated | Original framing — replaced by confirm prompt. | |
| req-dev-multisession-teardown-safety-3 | Partial-failure transparency | Deprecated | Replaced by per-step warnings + best-effort continuation. | |

## Manual Teardown (until the script lands)

Until `scripts/despawn-session.sh` is implemented, follow this sequence by hand for session `<name>`:

```bash
NAME=<name>
REPO=~/Documents/code/tap
cd ~/tap-sessions/$NAME
git status                                        # confirm clean
scripts/dc down -v --remove-orphans

cd $REPO
git worktree remove ~/tap-sessions/$NAME
git branch -D session/$NAME

# Free the band for reuse — remove the registry row.
sed -i.bak "/^${NAME} /d" ~/tap-sessions/.registry && rm -f ~/tap-sessions/.registry.bak
```

Verify with the commands in [Total Cleanup → Verification](#verification).

## Status Vocabulary

Standard TAP states: `Proposed`, `Approved for Development`, `In Development`, `Implemented`, `Verified`, `Refactoring`, `Deprecating`, `Deprecated`.
