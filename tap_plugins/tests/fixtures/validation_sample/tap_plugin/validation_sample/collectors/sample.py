"""SampleCollector — a no-op collector for the validation_sample fixture.

validate_plugin's `runs` level never invokes collectors (it only exercises
create_node / create_edge / grift_import), so this collector deliberately does
nothing and writes no grid state. It exists solely so the fixture is a faithful,
complete plugin that declares one collector like a real one would.
"""

from __future__ import annotations

from tap_cares.collectors import CollectorBase


class SampleCollector(CollectorBase):
    """Emit nothing; touch no grid state."""

    def run(self) -> None:
        self.summary = "validation_sample no-op collector: nothing to collect."
