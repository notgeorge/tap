"""Genericom EC2 Instance Hero — plugin-owned panel type.

Renders a hero header (instance name + aggregated verdict pill) plus a compact
identity card (instance type, account, VPC, subnet, IPs) for the EC2 instance
page. Reads `entity_id` from the page's URL params and runs a single gryphon
slice for both surfaces.

Spec: plugins/genericom/specs/spec-genericom-ec2-projection.md
      (req-genericom-ec2-hero, req-genericom-ec2-identity)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, ClassVar

_VERDICT_PRIORITY_AGG = {"violation": 3, "passing": 2, "informational": 1}


def _aggregate_verdict(evidence_list: list[dict[str, Any]]) -> str:
    best = ("", 0)
    for ev in evidence_list:
        sk = ev.get("support_kind") or ""
        weight = _VERDICT_PRIORITY_AGG.get(sk, 0)
        if weight > best[1]:
            best = (sk, weight)
    return best[0]

if TYPE_CHECKING:
    from django.http import HttpRequest

    from tap_web.models import Panel

logger = logging.getLogger(__name__)


class GenericomInstanceHeroPanelType:
    slug: ClassVar[str] = "genericom-ec2-instance-hero"
    label: ClassVar[str] = "Genericom EC2 Instance Hero"
    view: ClassVar[str] = "genericom/panels/instance_hero.html"
    css: ClassVar[list[str]] = ["genericom/css/panel-instance-hero.css"]
    js: ClassVar[list[str]] = []
    config_defaults: ClassVar[dict[str, Any]] = {}

    @classmethod
    def get_view_context(cls, panel: Panel, request: HttpRequest) -> dict[str, Any]:
        entity_id = request.GET.get("entity_id", "")
        if not entity_id:
            return {"hero_error": "No instance specified.", "hero": None}

        try:
            from tap_grid.models import Search
            from tap_grid.search import execute_search

            search = Search(
                search_type="gryphon",
                root="node",
                name="genericom-ec2-instance-hero",
                input_schema={
                    "type": "object",
                    "properties": {"entity_id": {"type": "string", "format": "uuid"}},
                    "required": ["entity_id"],
                },
                definition={
                    "query": [
                        "MATCH (asset:aws_ec2_instance)-[hf:HAS_FINDING]->(f:finding) WHERE asset.entity_id = $entity_id",
                        "MATCH (asset2:aws_ec2_instance)-[r:RESIDES_IN]->(s:aws_subnet) WHERE asset2.entity_id = $entity_id",
                        "MATCH (asset3:aws_ec2_instance)-[r2:RESIDES_IN]->(s2:aws_subnet)<-[ec:CONTAINS]-(v:aws_vpc)-[ba:BELONGS_TO_ACCOUNT]->(a:aws_account) WHERE asset3.entity_id = $entity_id",
                        "MATCH (asset4:aws_ec2_instance)-[h:HOSTS]->(iface:network_interface)-[hi:HAS_IP]->(ip:ip_address) WHERE asset4.entity_id = $entity_id",
                    ]
                },
                default_limit=200,
                max_limit=500,
            )
            result = execute_search(
                search, inputs={"entity_id": entity_id}, layer="extended"
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Instance hero search failed for %s", entity_id)
            return {"hero_error": f"Failed to load instance: {exc}", "hero": None}

        envelope = result["results"] if "results" in result else result
        nodes = envelope.get("nodes", [])
        edges = envelope.get("edges", [])

        nodes_by_id: dict[str, dict[str, Any]] = {}
        for n in nodes:
            ent = n.get("entity") or {}
            eid = ent.get("entity_id")
            if eid:
                nodes_by_id[eid] = n

        asset_node = nodes_by_id.get(entity_id)
        if asset_node is None:
            return {"hero_error": "Instance not found.", "hero": None}

        asset_ent = asset_node.get("entity") or {}
        asset_body = asset_node.get("node") or {}

        # Aggregate finding verdicts via HAS_FINDING → finding (-> HAS_EVIDENCE).
        # We only have a one-hop neighborhood here, so we collect verdicts from
        # the directly-linked findings; evidence aggregation per-finding is
        # deferred to the instance-findings panel below.
        finding_verdicts: list[dict[str, Any]] = []
        subnet_id: str = ""
        vpc_id: str = ""
        account_id: str = ""
        iface_to_ips: dict[str, list[str]] = {}
        for edge in edges:
            ebody = edge.get("edge") or {}
            etype = ebody.get("edge_type")
            from_id = ebody.get("from_entity_id")
            to_id = ebody.get("to_entity_id")
            if etype == "HAS_FINDING" and from_id == entity_id:
                fnode = nodes_by_id.get(to_id or "")
                if fnode is None:
                    continue
                fbody = fnode.get("node") or {}
                if (fbody.get("status") or "open") != "open":
                    continue
                finding_verdicts.append({"support_kind": "violation"})
            elif etype == "RESIDES_IN" and from_id == entity_id and to_id:
                subnet_id = to_id
            elif etype == "CONTAINED_BY" and from_id == subnet_id and to_id:
                vpc_id = to_id
            elif etype == "CONTAINS" and to_id == subnet_id and from_id:
                vpc_id = vpc_id or from_id
            elif etype == "BELONGS_TO_ACCOUNT" and from_id == vpc_id and to_id:
                account_id = to_id
            elif etype == "HOSTS" and from_id == entity_id:
                tnode = nodes_by_id.get(to_id or "")
                if tnode is None:
                    continue
                tent = tnode.get("entity") or {}
                if tent.get("entity_type") == "network_interface":
                    iface_to_ips.setdefault(to_id or "", [])
            elif etype == "HAS_IP" and from_id in iface_to_ips and to_id:
                ipnode = nodes_by_id.get(to_id) or {}
                ipent = ipnode.get("entity") or {}
                ipbody = ipnode.get("node") or {}
                label = (
                    ipbody.get("address")
                    or ipent.get("name")
                    or ipbody.get("name")
                    or ""
                )
                if label:
                    iface_to_ips[from_id].append(label)

        verdict = _aggregate_verdict(finding_verdicts) or "passing"

        def _name(eid: str) -> str:
            if not eid:
                return ""
            n = nodes_by_id.get(eid) or {}
            ent = n.get("entity") or {}
            body = n.get("node") or {}
            return ent.get("name") or body.get("name") or ""

        ip_labels: list[str] = []
        for ips in iface_to_ips.values():
            ip_labels.extend(ips)
        # Fall back to the asset's own private/public IP fields when no
        # interface→IP graph edges are seeded for this asset.
        if not ip_labels:
            for ip in (asset_body.get("private_ip"), asset_body.get("public_ip")):
                if ip:
                    ip_labels.append(ip)

        hero = {
            "name": asset_ent.get("name") or asset_body.get("name") or "",
            "verdict": verdict,
            "instance_type": asset_body.get("ec2_type") or asset_body.get("instance_type") or "",
            "private_ip": asset_body.get("private_ip") or "",
            "public_ip": asset_body.get("public_ip") or "",
            "account": _name(account_id),
            "vpc": _name(vpc_id),
            "subnet": _name(subnet_id),
            "ips": sorted(set(ip_labels)),
        }

        return {"hero_error": None, "hero": hero}
