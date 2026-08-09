# TAP — The Analogy Platform

TAP is a general-purpose platform for mastering the systems you are responsible
for — accounts, pipelines, fleets, data flows, the organization
itself — by modeling each as a live, queryable, visual representatiion called **the grid**:
nodes and edges fused with dimensions, batches, history, and field-level provenance,
so the model stays explainable as it changes.  
  
[TAP in two pages](docs/doc-tap-intro.md) is the fastest way in.

The grid is designed for humans and AI agents working together.  
  
The system lives in the battle-tested PostgreSQL database, is queried through
**Gryphon** (TAP's grid query language), data is exchanged as **GRIFT** files (its JSON graph
format), and functionality can be extended  through **plugins** — core speaks no domain language;
every vocabulary arrives as a plugin. 


> **Early access.** You're here before the polish. The system works — it is used
> daily against real infrastructure — but you will find rough edges, and reporting
> them is genuinely wanted: [open an issue](../../issues). A Discord is coming.

## Get it running

You need **git**, **Docker** (Desktop on macOS; Engine + the Compose v2 plugin on
Linux), and any **python3** on the host. 
  
  Linux users: read
[Host prerequisites (Linux)](docs/misc/doc-dev-multisession-onboarding.md#host-prerequisites-linux)
first — it covers the docker group, ports, and two known papercuts.

```bash
mkdir -p ~/tap-sessions
git clone <this repository> ~/tap-sessions/main
cd ~/tap-sessions/main
scripts/spawn-session.sh dev        # any session name you like
```

That's the whole procedure — first boot and every later session are the same
command. The script checks your host, creates an isolated session worktree at
`~/tap-sessions/dev`, pulls the published images (anonymous, multi-arch, with the
FIPS-validated OpenSSL provider and pre-compiled Python wheels baked in — offline or
unpublished it falls back to a local build, which compiles those from source in
10–20 minutes), boots the instance, and prints your URL and admin credentials.
Sign in with the password from the worktree's `.dev-credentials`, then enroll a
passkey from your session if you want one. Your next concurrent session is just
`scripts/spawn-session.sh <another-name>`.

The `~/tap-sessions/main` location matters: sessions are git worktrees beside it,
and the tooling standardizes on that layout (the script checks, and tells you how
to adopt it if you cloned somewhere else).

Profiles that pull live data declare the credentials they need
(`required_secrets` in the boot profile), and the boot preflight checks the
declarations in seconds — naming exactly what's missing or dead before anything
expensive runs, with the verdict persisted to `logs/boot/latest.boot-record.json`.
Your AI assistant closes the gaps with `/provision-secrets`, which reads the same
declaration and routes each credential to its plugin's canonical setup docs. The
default `core_dev` profile needs no credentials at all.

**The easier way: let your AI assistant drive.** Open an AI coding assistant in the
clone (Claude Code, or anything that reads this repo) and ask it to get TAP running —
the `/get-started` skill walks it through host prep, the choices, the run, and the
first login, and it can diagnose anything that goes wrong. This repo treats AI
assistants as first-class operators: skills under `*/skills/` are step-by-step
procedures written for them.

Day to day: 
- `scripts/dc up -d`
-  `scripts/dc down`
-  `scripts/dc logs -f web`.
  
All of these run from inside a session worktree (`~/tap-sessions/<name>`).
To pick up new code, spawn a fresh session from the updated main
(`git -C ~/tap-sessions/main pull`, then `scripts/spawn-session.sh <new-name>`) —
sessions are cheap and disposable (`scripts/despawn-session.sh <name>`).

## Build your own plugin

Everything domain-specific in TAP is a plugin — node and edge types, collectors that
pull real data in, pages and panels that show it. Ask your assistant to run
`/new-plugin`, or start from `tap_plugins/specs/spec-plugin-external-development.md`,
which is the contract for developing plugins against this repo as your harness.
Boot profiles (`boot/*.boot.json`) declare which plugins an instance runs and where
they install from.

The reference deployment is **samsite** — a real, deployed website whose AWS
infrastructure, GitHub pipeline, and published signed artifacts all land on the
grid. Its boot record ships inside the plugin and boots by pointer:
`scripts/spawn-session.sh demo cli --from git+https://github.com/unified-systems-com/tap-plugin-samsite@v0.2.0#samsite`.
Its plugin README documents what it takes to point that machinery at your own
deployment, credentials included.

## Finding your way

| Where | What |
| --- | --- |
| [`docs/doc-tap-intro.md`](docs/doc-tap-intro.md) | TAP in two pages — start here |
| `architecture.md` | The architectural contract behind it |
| `AGENTS.md` / `CLAUDE.md` | Orientation for AI assistants working in this repo |
| `specs/`, `<app>/specs/` | Behavior contracts — the canonical source of truth |
| `tap_grid/` | The graph core: entity spine, edges, service layer, Gryphon, GRIFT |
| `boot/` | Boot profiles — what an instance installs and seeds |
| `*/skills/` | AI-operable procedures (stand up, add a model, build a collector, …) |

## License

Apache-2.0 — see [LICENSE](LICENSE) and [NOTICE](NOTICE).
