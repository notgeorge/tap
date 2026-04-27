---
spec: ../specs/spec-dev-playwright-refresh-doc.md
audience: [llm, developer]
covers:
  - ../specs/spec-dev-playwright-refresh.md
  - req-dev-playwright-refresh-script
  - req-dev-playwright-refresh-restart
  - req-dev-playwright-refresh-scope
update-triggers:
  - scripts/refresh-playwright.sh behavior or output
  - Playwright MCP package name or invocation
  - Claude Code restart mechanics
  - MCP server registration in .claude/ settings
  - Adoption of a self-restart / hook-based recovery
assumes:
  - macOS / zsh shell (the only environment exercised today)
  - pgrep / kill / xargs available on PATH
  - the reader is an attached Claude Code session OR a developer with shell access
provides: |
  Reader can detect a wedged Playwright MCP server, run the refresh script,
  and hand off to a clean Claude Code session — without escalating to the
  human owner of the project.
---

# Refreshing the Playwright MCP Server

Spec: [spec-dev-playwright-refresh-doc.md](../specs/spec-dev-playwright-refresh-doc.md)

This is the canonical procedure for an attached Claude Code session (or a developer) to recover from a wedged Playwright MCP server. The companion feature spec is [spec-dev-playwright-refresh.md](../specs/spec-dev-playwright-refresh.md).

## 1. Detect that you actually need this doc

Run this procedure when one or more symptoms are visible:

- `mcp__playwright__browser_*` calls hang or time out.
- Playwright returns "browser already closed" / "target closed" errors that don't recover after navigation.
- A Chromium window is open with no MCP attached, left over from a previous crashed session.
- Tool schemas come back but every call fails immediately.

If none of those apply, the issue is probably not a wedged MCP — stop and diagnose elsewhere instead of restarting.

## 2. Run the refresh script

```bash
scripts/refresh-playwright.sh
```

Expected output, one of:

- `No Playwright MCP processes found.` — there was nothing to clean up. The wedge is somewhere else; do not proceed to step 3.
- `Killing PIDs: <pids>` followed by `Done. All Playwright MCP processes killed.` — cleanup succeeded.

The script also kills parent npm processes matching `@playwright/mcp` so the MCP socket is fully released. It is safe to re-run; running on a clean system is a no-op (see [req-dev-playwright-refresh-script](../specs/spec-dev-playwright-refresh.md#refresh-script)).

## 3. Hand off to a fresh Claude Code session — **HUMAN ACTION REQUIRED**

Killing the MCP processes does not reset Claude Code's existing MCP connection. The current Claude session must exit and be relaunched so the harness spawns a fresh MCP child.

If you are an attached Claude session, you cannot relaunch yourself. Tell the human:

> Playwright MCP refresh complete. Please exit this Claude Code session (Ctrl-D or type `/exit`) and relaunch with `claude` so a fresh MCP connection is created.

If you are the human, do exactly that.

## 4. Verify recovery in the new session

After relaunching, in the new Claude Code session:

```
mcp__playwright__browser_navigate { url: "http://localhost:8000/" }
```

A clean snapshot returning a page title proves the MCP is live again. If it still fails, the issue is not a wedged MCP — escalate.

## When this doc does not apply

- The Playwright MCP server is not registered in your `.claude/` config — restarting will not help; check MCP registration first.
- The browser hangs because the *site under test* is broken, not the MCP — verify with `curl` first.
- You are debugging Playwright test scripts (not MCP) — that is a different stack and this doc does not apply.

## Future

A self-restart hook may replace step 3 (see Future in [spec-dev-playwright-refresh.md](../specs/spec-dev-playwright-refresh.md#future)). Until that lands, step 3 is the unavoidable human handoff.
