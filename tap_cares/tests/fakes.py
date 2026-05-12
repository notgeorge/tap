"""Fake CollectorBase subclasses used in tap_cares tests."""

from __future__ import annotations

from tap_cares.collectors import CollectorBase


class HappyCollector(CollectorBase):
    """A collector whose run() always succeeds."""

    runs: list[str] = []

    def run(self) -> None:
        HappyCollector.runs.append(str(self.config.collection_job_entity_id))


class BoomCollector(CollectorBase):
    """A collector whose run() always raises."""

    def run(self) -> None:
        raise RuntimeError("boom from BoomCollector")


class _UnregisteredCollector(CollectorBase):
    """A collector class that is intentionally never registered."""

    def run(self) -> None:
        return None
