"""Tests for the Genericom demonstration plugin.

Covers:
  - plugin structure and manifest validation
  - GRIFT bundle import round-trip for all six bundles
  - expected node and edge counts per spec
  - tap.env=genericom-prod dimension propagation onto imported entities
  - request-path traversability: Route 53 -> ALB -> TargetGroup -> EC2 -> RDS
  - finding-intent stash in _reserved survives in the shipped GRIFT files
"""

import json
from pathlib import Path

import pytest

from tap_grid.grift import grift_import
from tap_grid.models import Edge, Entity
from tap_plugins.validate.service import validate_plugin

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
GRIFT_DIR = PLUGIN_ROOT / "grift"
AWS_CORE_GRIFT_DIR = PLUGIN_ROOT.parent / "aws_core" / "grift"

BUNDLES = ("dimension", "account", "network", "dns", "web", "data")


def _load_bundle(name: str) -> dict:
    return json.loads((GRIFT_DIR / f"{name}.grift.json").read_text())


def _import_all_bundles() -> None:
    """Seed aws_core region/AZ prerequisites, then import every Genericom bundle."""
    for name in ("dimension", "regions"):
        aws_doc = json.loads((AWS_CORE_GRIFT_DIR / f"{name}.grift.json").read_text())
        result = grift_import(aws_doc, dangling_edge_mode="error", actor=None)
        assert result.success, f"aws_core bundle '{name}' import failed: {result.errors}"

    for name in BUNDLES:
        result = grift_import(_load_bundle(name), dangling_edge_mode="error", actor=None)
        assert result.success, f"Bundle '{name}' import failed: {result.errors}"


class TestGenericomStructure:
    def test_structure_passes(self):
        result = validate_plugin(PLUGIN_ROOT, level="structure")
        assert result.ok, result.to_human()


class TestGenericomManifest:
    def test_manifest_declares_six_bundles(self):
        result = validate_plugin(PLUGIN_ROOT, level="structure")
        manifest_check = next(c for c in result.checks if c.id == "manifest-parse")
        assert manifest_check.status == "pass"
        assert any("6 grift bundle(s)" in m.text for m in manifest_check.messages)

    def test_manifest_declares_no_models_or_edges(self):
        """Genericom is data-only — it should not introduce new models or edge types."""
        import tomllib

        toml = tomllib.loads((PLUGIN_ROOT / "tap-plugin.toml").read_text())
        assert "models" not in toml
        assert "edges" not in toml

    def test_all_bundles_referenced_files_exist(self):
        import tomllib

        toml = tomllib.loads((PLUGIN_ROOT / "tap-plugin.toml").read_text())
        for name, rel_path in toml["grift"].items():
            assert (PLUGIN_ROOT / rel_path).exists(), f"Missing GRIFT file for '{name}': {rel_path}"


@pytest.mark.django_db(transaction=True)
class TestGenericomImport:
    """Full import round-trip for all six GRIFT bundles."""

    def test_all_bundles_import_cleanly(self):
        _import_all_bundles()

    def test_node_counts_match_spec(self):
        _import_all_bundles()

        expected = {
            "dimension": 1,          # tap.env: genericom-prod
            "aws_account": 1,        # genericom-prod
            "aws_vpc": 1,            # genericom-prod-vpc
            "aws_internet_gateway": 1,
            "aws_subnet": 6,         # two per tier x three tiers
            "aws_route53_zone": 1,
            "aws_acm_certificate": 1,
            "aws_alb": 1,
            "aws_target_group": 1,
            "aws_ec2_instance": 2,   # web-a, web-c
            "aws_rds_instance": 1,
        }

        for entity_type, count in expected.items():
            got = Entity.objects.filter(
                entity_type=entity_type, dimensions__contains={"tap.env": "genericom-prod"}
            ).count()
            if entity_type == "dimension":
                # Dimension nodes carry tap.meta, not tap.env; match by name.
                got = Entity.objects.filter(
                    entity_type="dimension", name="tap.env: genericom-prod"
                ).count()
            assert got == count, f"Expected {count} '{entity_type}' in genericom-prod, got {got}"

    def test_edge_counts_match_spec(self):
        _import_all_bundles()

        # Every Genericom-owned edge carries tap.env=genericom-prod.
        genericom_edges = Edge.objects.filter(entity__dimensions__contains={"tap.env": "genericom-prod"})
        # 15 network + 2 dns + 9 web + 5 data = 31 edges total
        assert genericom_edges.count() == 31

        from collections import Counter

        edge_types = Counter(genericom_edges.values_list("edge_type", flat=True))
        # 4 BELONGS_TO (VPC, Route53, ACM, RDS -> account)
        # 7 CONTAINS (region->VPC + VPC->6 subnets)
        # 1 ATTACHED_TO (IGW -> VPC)
        # 12 RESIDES_IN (6 subnet->AZ + 2 ALB->subnet + 2 EC2->subnet + 2 RDS->subnet)
        # 3 BACKED_BY (ALB->cert, TG->EC2a, TG->EC2c)
        # 2 ROUTES_TO (Route53->ALB, ALB->TG)
        # 2 STORES_IN (each EC2 -> RDS)
        assert edge_types == {
            "BELONGS_TO": 4,
            "CONTAINS": 7,
            "ATTACHED_TO": 1,
            "RESIDES_IN": 12,
            "BACKED_BY": 3,
            "ROUTES_TO": 2,
            "STORES_IN": 2,
        }


@pytest.mark.django_db(transaction=True)
class TestGenericomDimensions:
    """Imported Genericom entities carry both tap.cloud=aws and tap.env=genericom-prod."""

    def test_vpc_carries_both_dimensions(self):
        _import_all_bundles()
        vpc = Entity.objects.get(entity_type="aws_vpc", name="genericom-prod-vpc")
        assert vpc.dimensions == {"tap.cloud": "aws", "tap.env": "genericom-prod"}

    def test_alb_carries_both_dimensions(self):
        _import_all_bundles()
        alb = Entity.objects.get(entity_type="aws_alb", name="genericom-prod-web-alb")
        assert alb.dimensions == {"tap.cloud": "aws", "tap.env": "genericom-prod"}

    def test_rds_carries_both_dimensions(self):
        _import_all_bundles()
        rds = Entity.objects.get(entity_type="aws_rds_instance", name="genericom-prod-postgres")
        assert rds.dimensions == {"tap.cloud": "aws", "tap.env": "genericom-prod"}

    def test_edge_carries_tap_env_dimension(self):
        _import_all_bundles()
        # Pick an IGW->VPC ATTACHED_TO edge
        igw = Entity.objects.get(entity_type="aws_internet_gateway")
        edge = Edge.objects.get(from_entity=igw, edge_type="ATTACHED_TO")
        assert edge.entity.dimensions.get("tap.env") == "genericom-prod"
        # ATTACHED_TO has no registered default_dimensions in aws_core so no tap.cloud
        # (and that's fine — the env scope is what matters for Genericom).

    def test_dimension_node_self_tagged(self):
        _import_all_bundles()
        dim = Entity.objects.get(entity_type="dimension", name="tap.env: genericom-prod")
        assert dim.dimensions == {"tap.meta": "dimension"}


@pytest.mark.django_db(transaction=True)
class TestGenericomRequestPath:
    """The request path Route53 -> ALB -> TG -> EC2 -> RDS is traversable."""

    def test_route53_routes_to_alb(self):
        _import_all_bundles()
        zone = Entity.objects.get(entity_type="aws_route53_zone", name="genericom.com")
        edge = Edge.objects.get(from_entity=zone, edge_type="ROUTES_TO")
        assert edge.to_entity.entity_type == "aws_alb"

    def test_alb_routes_to_target_group(self):
        _import_all_bundles()
        alb = Entity.objects.get(entity_type="aws_alb")
        edge = Edge.objects.get(from_entity=alb, edge_type="ROUTES_TO")
        assert edge.to_entity.entity_type == "aws_target_group"

    def test_target_group_backed_by_two_ec2s(self):
        _import_all_bundles()
        tg = Entity.objects.get(entity_type="aws_target_group")
        backends = Edge.objects.filter(from_entity=tg, edge_type="BACKED_BY")
        ec2_names = sorted(e.to_entity.name for e in backends)
        assert ec2_names == ["genericom-prod-web-a", "genericom-prod-web-c"]

    def test_each_ec2_stores_in_rds(self):
        _import_all_bundles()
        web_a = Entity.objects.get(entity_type="aws_ec2_instance", name="genericom-prod-web-a")
        web_c = Entity.objects.get(entity_type="aws_ec2_instance", name="genericom-prod-web-c")
        for ec2 in (web_a, web_c):
            edge = Edge.objects.get(from_entity=ec2, edge_type="STORES_IN")
            assert edge.to_entity.name == "genericom-prod-postgres"

    def test_alb_backed_by_acm_cert(self):
        _import_all_bundles()
        alb = Entity.objects.get(entity_type="aws_alb")
        edge = Edge.objects.get(from_entity=alb, edge_type="BACKED_BY")
        assert edge.to_entity.entity_type == "aws_acm_certificate"


class TestGenericomFindingIntentStash:
    """req-genericom-demo-finding-stash: finding intents are preserved in _reserved
    blocks of GRIFT files shipping finding-bearing nodes.
    """

    def test_web_bundle_carries_alb_finding_intents(self):
        doc = _load_bundle("web")
        intents = doc["_reserved"].get("finding_intent", [])
        slugs = {i["slug"] for i in intents}
        assert "genericom-alb-public-http-80" in slugs
        assert "genericom-alb-internal-http" in slugs

    def test_data_bundle_carries_rds_finding_intent(self):
        doc = _load_bundle("data")
        intents = doc["_reserved"].get("finding_intent", [])
        slugs = {i["slug"] for i in intents}
        assert "genericom-rds-unencrypted-at-rest" in slugs

    def test_finding_intents_reference_entities_in_their_own_bundle(self):
        """Every finding_intent.target_entity_id points at a node in the same bundle."""
        for name in ("web", "data"):
            doc = _load_bundle(name)
            intents = doc["_reserved"].get("finding_intent", [])
            if not intents:
                continue
            node_ids = {n["entity"]["entity_id"] for b in doc["batches"] for n in b["nodes"]}
            for intent in intents:
                assert intent["target_entity_id"] in node_ids, (
                    f"finding_intent {intent['slug']} in '{name}' bundle "
                    f"points at entity_id {intent['target_entity_id']} not present in bundle"
                )

    def test_finding_intents_cite_spec_acid(self):
        for name in ("web", "data"):
            doc = _load_bundle(name)
            for intent in doc["_reserved"].get("finding_intent", []):
                assert intent["spec_ref"].startswith("req-genericom-demo-findings-")
