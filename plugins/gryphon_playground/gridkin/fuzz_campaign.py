"""Append-only ledger + trend for Gryphon fuzz campaigns (`req-gridkin-fuzz-campaign`).

The engine (`tests/test_gryphon_fuzz_campaign.py`) grinds one fresh seed band and
writes a summary JSON. This module owns the durable side: pick the next fresh
band (so campaigns never re-test fixed seeds), append one stamped row per
campaign to a JSONL ledger, and render the trend the whole exercise exists for —
**distinct new defects per 100k queries over fresh seed space, declining as the
executor hardens**, with the oracle-asserted fraction beside it so a falling rate
cannot be a generator that quietly stopped exploring.

Stdlib-only by design: the bash orchestrator imports it in-container without
Django setup (the `gridkin` package `__init__` is import-light), and it never
touches the DB or the executor. A ledger row is one campaign summary plus the
`commit` / `utc` the orchestrator stamps on.
"""

from __future__ import annotations

import json
import os
from typing import Any

DEFAULT_START_SEED = 1_000_000  # well clear of the committed gate seed (1729) and soak bands


def _read_rows(ledger_path: str) -> list[dict[str, Any]]:
    """Load every campaign row from the JSONL ledger (missing file → empty)."""
    if not os.path.exists(ledger_path):
        return []
    rows: list[dict[str, Any]] = []
    with open(ledger_path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def next_base_seed(ledger_path: str, default_start: int = DEFAULT_START_SEED) -> int:
    """The first seed of the next band: one past the highest `seed_end` on record.

    Advancing monotonically is load-bearing — divergences are deterministic, so a
    re-run of a prior band reports zero regardless of executor state. Fresh
    territory is the only honest measurement.
    """
    rows = _read_rows(ledger_path)
    if not rows:
        return default_start
    return max(int(r["seed_end"]) for r in rows) + 1


def append_row(ledger_path: str, summary: dict[str, Any], *, commit: str, utc: str) -> dict[str, Any]:
    """Stamp a campaign summary with commit/utc and append it as one JSONL line."""
    row = {"utc": utc, "commit": commit, **summary}
    os.makedirs(os.path.dirname(ledger_path) or ".", exist_ok=True)
    with open(ledger_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def _fingerprints(row: dict[str, Any]) -> set[str]:
    return {d["fingerprint"] for d in row.get("defects", [])}


def trend(ledger_path: str, last_n: int = 20) -> str:
    """Render the campaign trend table: newest `last_n` rows, oldest first.

    `new` counts a row's defect fingerprints not seen in ANY earlier campaign —
    the sharpest down-and-to-the-right signal ("are we still finding NEW bugs?").
    `def/100k` is that campaign's distinct-defect density. `asrt%` is the
    oracle-asserted fraction (the exploration-collapse guard).
    """
    rows = _read_rows(ledger_path)
    if not rows:
        return "no campaigns recorded yet."

    seen: set[str] = set()
    lines = [
        f"Gryphon fuzz-campaign trend — {len(rows)} campaign(s), "
        f"{sum(r['n_queries'] for r in rows):,} queries, "
        f"{len(set().union(*(_fingerprints(r) for r in rows))) if rows else 0} distinct defects all-time",
        f"{'utc':20}  {'commit':8}  {'band':>19}  {'queries':>8}  {'asrt%':>6}  {'distinct':>8}  {'def/100k':>9}  {'new':>4}",
    ]
    display_start = max(0, len(rows) - last_n)
    for idx, r in enumerate(rows):
        fps = _fingerprints(r)
        new = len(fps - seen)
        seen |= fps
        if idx < display_start:
            continue
        n_q = int(r["n_queries"]) or 1
        band = f"{r['base_seed']}-{r['seed_end']}"
        per_100k = round(int(r["distinct_defects"]) * 100_000 / n_q, 2)
        lines.append(
            f"{str(r.get('utc', '?'))[:20]:20}  {str(r.get('commit', '?')):8}  {band:>19}  "
            f"{n_q:>8}  {float(r.get('asserted_fraction', 0)) * 100:>5.1f}  "
            f"{int(r['distinct_defects']):>8}  {per_100k:>9}  {new:>4}"
        )
    return "\n".join(lines)
