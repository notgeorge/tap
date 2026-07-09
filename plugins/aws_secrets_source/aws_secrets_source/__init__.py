"""AWS Secrets Manager secret-source provider for TAP.

Source-only distribution (not a grid plugin): it contributes a single
``tap.secret_sources`` provider so TAP can resolve a secret's *value* from AWS Secrets
Manager while the manifest stays disk-resident and TAP-owned. See ``source.py`` and
``specs/spec-plugin-dependency-resolution.md`` ``req-plugin-depres-sources``.
"""
