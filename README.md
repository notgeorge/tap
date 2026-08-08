# TAP — The Analogy Platform

TAP is a systems-mastery platform: it models a real system — cloud infrastructure, a
deploy pipeline, a compliance program — as a live, queryable, visual graph, built for
humans and AI assistants working together. The graph lives in ordinary PostgreSQL (an
entity spine + first-class edges, with per-field history and provenance), queried
through **Gryphon** (TAP's graph query language), interchanged as **GRIFT** (its JSON
graph format), and extended entirely through **plugins** that bring their own types,
collectors, pages, and dashboards.

**Rampart** is the first product built on TAP — a security/compliance assessment
surface with a FedRAMP 20x story. The UI badges itself `RAMPART` by default; you are
running TAP either way (`TAP_PRODUCT_NAME` controls the label).

> **Early access.** You're here before the polish. The system works — it is used
> daily against real infrastructure — but you will find rough edges, and reporting
> them is genuinely wanted: [open an issue](../../issues). A Discord is coming.

## Get it running

You need **git**, **Docker** (Desktop on macOS; Engine + the Compose v2 plugin on
Linux), and any **python3** on the host. Linux desks: read
[Host prerequisites (Linux)](docs/misc/doc-dev-multisession-onboarding.md#host-prerequisites-linux)
first — it covers the docker group, ports, and two known papercuts.

```bash
git clone <this repository> tap && cd tap
scripts/stand-up.sh
```

That's the whole procedure. The script checks your host, builds the image (the first
build compiles the FIPS-validated OpenSSL provider — 10–20 minutes, once; every later
start is seconds), boots the instance, and prints your URL and admin credentials.
Sign in with the password from `.dev-credentials`, then enroll a passkey from your
session if you want one.

**The better way: let your AI assistant drive.** Open an AI coding assistant in the
clone (Claude Code, or anything that reads this repo) and ask it to stand TAP up —
the `/stand-up` skill walks it through host prep, the choices, the run, and the
first login, and it can diagnose anything that goes wrong. This repo treats AI
assistants as first-class operators: skills under `*/skills/` are step-by-step
procedures written for them.

Day to day: `scripts/dc up -d` / `scripts/dc down` / `scripts/dc logs -f web`.
To update: `git pull && scripts/dc up -d --build` (migrations run on start).

## Build your own plugin

Everything domain-specific in TAP is a plugin — node and edge types, collectors that
pull real data in, pages and panels that show it. Ask your assistant to run
`/new-plugin`, or start from `tap_plugins/specs/spec-plugin-external-development.md`,
which is the contract for developing plugins against this repo as your harness.
Boot profiles (`boot/*.boot.json`) declare which plugins an instance runs and where
they install from.

The reference deployment is **samsite** — a real, deployed website whose AWS
infrastructure, GitHub pipeline, and signed compliance artifacts all land on the
grid. Its plugin README documents what it takes to point that machinery at your own
deployment, credentials included.

## Finding your way

| Where | What |
| --- | --- |
| `architecture.md` | The system in one read — start here |
| `AGENTS.md` / `CLAUDE.md` | Orientation for AI assistants working in this repo |
| `specs/`, `<app>/specs/` | Behavior contracts — the canonical source of truth |
| `tap_grid/` | The graph core: entity spine, edges, service layer, Gryphon, GRIFT |
| `boot/` | Boot profiles — what an instance installs and seeds |
| `*/skills/` | AI-operable procedures (stand up, add a model, build a collector, …) |

## License

Apache-2.0 — see [LICENSE](LICENSE) and [NOTICE](NOTICE).
