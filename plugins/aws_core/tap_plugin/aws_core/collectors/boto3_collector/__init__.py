"""boto3 AWS collector — the make-it-work boto3-backed aws_core collector.

Each aws_core collector lives in its own ``collectors/<name>_collector/``
package so that, with multiple collectors, it is always clear which one you
are looking at. This package holds the manifest-driven boto3 collector: the
resource manifest + its JSON Schema (``aws_resource_manifest.json`` /
``aws_resource_manifest.schema.json``) and, as it is built, the generic
engine and the ``CollectorBase`` subclass.

Spec: plugins/aws_core/specs/spec-aws-core-collector-v0.md
"""
