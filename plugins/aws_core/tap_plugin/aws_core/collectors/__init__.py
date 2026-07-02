"""AWS Core collector implementations.

Each collector lives in its own ``<name>_collector/`` subpackage so that
with multiple collectors it is always clear which one you are looking at
(e.g. ``boto3_collector/``). A collector subpackage owns its manifest,
schema, engine, and ``CollectorBase`` subclass; collectors register with
tap_cares in ``plugins/aws_core/apps.py``.

The Steampipe collector stack was excised on 2026-05-17 (parked at git tag
``park/steampipe-tooling``); the from-scratch boto3 collector is in
``boto3_collector/``.
"""
