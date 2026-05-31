# After-Action Reports (AAR)

Retrospectives on the **development process** — sprints, decisions, or autonomous
runs that went sideways. The subject is *how we worked*, not what the running
system did. Audience: improving agent/human workflow (scope discipline,
definition-of-done, validation honesty).

This is one of two co-located incident corpora under `docs/`:

- **`docs/aar/`** (here) — the *process* went wrong. Feeds workflow/collaboration
  rules in `AGENTS.md` + agent memory.
- **[`docs/postmortems/`](../postmortems/)** — the *running instance's state* went
  wrong (a bug/runtime/UX defect in TAP itself). Feeds the **Paladin** healer.

Same neighborhood, different question: "did we work well?" vs. "did the system
behave well?" Cross-link freely when one caused the other.

## Standardized format & filing

The section structure (8 sections: Goal vs Outcome / Timeline / What Went Well /
What Went Wrong / Root Causes / Impact / Corrective Actions / Lessons → Durable
Rules) is defined at the end of the first report,
[`2026-05-16-aws-collector-sprint-sprawl.md`](2026-05-16-aws-collector-sprint-sprawl.md).

Filing convention: `docs/aar/<YYYY-MM-DD>-<short-slug>.md`.
