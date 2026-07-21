"""validation_sample — minimal fixture plugin for the validate_plugin test suite.

Ships one unconstrained BaseModel (``validation_sample__sample_node``), one
wildcard-endpoint edge (``SAMPLE_LINK__validation_sample``), and one no-op
collector. Its only job is to be a real, installable, package-mode plugin that
``tap_plugins.validate.service.validate_plugin`` can validate at all three levels
(structure / loads / runs) now that every domain plugin lives in its own repo.
"""
