"""The Gridkin runner — one pytest item per discovered scenario.

Scenarios are discovered and JSON-Schema-validated at collection time; a
malformed `.gridkin.json` fails collection loudly. Each scenario seeds its
GRIFT fixture into a freshly-isolated test database, executes the Gryphon
query, and asserts the response envelope and the captured SQL against committed
oracle files.

Run a subset with `pytest -m gridkin -k <fragment>`; regenerate oracle files
with `GRIDKIN_UPDATE_SNAPSHOTS=1`. See spec-gridkin-v0.md.
"""

from __future__ import annotations

import pytest

from plugins.gryphon_playground.gridkin import loader, runner

_SCENARIOS = loader.discover_scenarios()
_UPDATE_SNAPSHOTS = loader.env_flag("GRIDKIN_UPDATE_SNAPSHOTS")


@pytest.mark.gridkin
@pytest.mark.django_db(transaction=True, databases=["default", "search_readonly"])
@pytest.mark.parametrize(
    "scenario",
    _SCENARIOS,
    ids=[scenario.scenario_id for scenario in _SCENARIOS],
)
def test_gridkin_scenario(scenario):
    failures = runner.run_scenario(scenario, update_snapshots=_UPDATE_SNAPSHOTS)
    assert not failures, "\n\n".join(failures)
