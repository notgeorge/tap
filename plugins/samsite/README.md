# Samsite plugin

What it owns:
- The landing page that projects the live AWS infrastructure backing the
  cross-deployed Sam Aydlette site (account 180731181784, us-east-1 +
  us-east-2).

What it does NOT own:
- AWS resource models or edges — those live in `plugins/aws_core/`.
- The boto3 collector — same. Samsite is a projection/page plugin.

First-pass behavior (2026-05-20):
- Mints a single `aws_account` node for account 180731181784 using the
  same deterministic uuid5 scheme the boto3 collector uses, so when the
  collector eventually emits this node itself the IDs collide cleanly.
- Mounts a single Cytoscape graph panel under `/samsite`.
- Designates this page as the site's default landing page (supersedes
  genericom's prior landing batch via a higher-version `landing_page`).
- Projection JS synthesizes "everything sits inside the aws_account" via
  each resource's `aws_account` dimension — no per-edge GRIFT bookkeeping.

Strategy notes and decisions: `plan/strat-sam-demo.md`.
