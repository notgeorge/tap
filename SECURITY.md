# Security Policy

TAP is in early access: it is used daily against real infrastructure, but it
is young software. Security reports are genuinely wanted — this page tells you
how to make one and what to expect.

## Reporting a vulnerability

Report vulnerabilities privately through GitHub's
[private vulnerability reporting](https://github.com/unified-systems-com/tap/security/advisories/new)
— the "Report a vulnerability" button under this repository's **Security** tab.

**Please do not open a public issue for a suspected vulnerability.**

A useful report includes the affected surface (endpoint, component, or file),
steps to reproduce, and what an attacker gains. Proof-of-concept material is
welcome but not required.

## What to expect

- **Acknowledgment within 7 days** of your report.
- **Initial assessment within 14 days** — whether we confirm it, how severe we
  think it is, and roughly what happens next.
- We will keep you informed as a fix progresses, and may ask follow-up
  questions.

## Supported versions

TAP is pre-release. The latest `main` and the latest published container
images are the only supported versions; fixes land there and are not
backported. This section will be replaced with a supported-versions statement
when versioned releases begin.

## Scope

In scope:

- This repository (TAP core).
- Plugins owned by the `unified-systems-com` organization — report against the
  affected plugin repository if you can tell which it is, or here if unsure.

Out of scope:

- **Plugins not owned by `unified-systems-com`** — report those to their
  maintainers.
- **Vulnerabilities in upstream dependencies** — report those upstream, but do
  tell us if TAP's *usage* of the dependency is what makes it exploitable.
- **Operator misconfiguration of self-hosted deployments.**
- **The local development workflow** (session spawning, dev-mode
  conveniences). Hardening suggestions for dev ergonomics are welcome as
  regular issues, but dev mode is not a production surface.

## Disclosure

We follow coordinated disclosure:

- We ask that you give us a reasonable window (90 days is a fine default)
  before disclosing publicly.
- When a fix ships we publish a GitHub security advisory, credit the reporter
  (unless you prefer anonymity), and request a CVE where warranted.

There is no bug bounty program at this time.
