"""Unit tests for the RGTA sweep (boto3-free, no DB).

Covers req-aws-collector-tags -2/-7: ResourceARN→{str:str} map across
pages, filter derivation, and the restart-once-on-token-expiry contract.
"""

from __future__ import annotations

import pytest
from botocore.exceptions import ClientError

from plugins.aws_core.collectors.boto3_collector.rgta import (
    rgta_resource_type_filters,
    sweep_tags,
)


def _client_error(code: str) -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": code}}, "GetResources")


class _Paginator:
    def __init__(self, pages, *, raise_first=None):
        self._pages = pages
        self._raise_first = raise_first
        self.calls = 0

    def paginate(self, **_kw):
        self.calls += 1
        if self._raise_first and self.calls == 1:
            raise self._raise_first
        yield from self._pages


class _Client:
    def __init__(self, pages, *, raise_first=None):
        self._pag = _Paginator(pages, raise_first=raise_first)

    def get_paginator(self, _name):
        return self._pag


_PAGES = [
    {
        "ResourceTagMappingList": [
            {"ResourceARN": "arn:fn:a", "Tags": [{"Key": "Owner", "Value": "sam"}]},
            {"ResourceARN": "arn:fn:b", "Tags": []},
        ]
    },
    {
        "ResourceTagMappingList": [
            {"ResourceARN": "arn:fn:c", "Tags": [{"Key": "Env", "Value": "prod"}]},
            {"Tags": [{"Key": "x", "Value": "y"}]},  # no ARN -> skipped
        ]
    },
]


class TestSweepTags:
    def test_builds_normalized_map_across_pages(self):
        out = sweep_tags(_Client(_PAGES), ["lambda:function"])
        assert out == {
            "arn:fn:a": {"Owner": "sam"},
            "arn:fn:b": {},
            "arn:fn:c": {"Env": "prod"},
        }

    def test_empty_filters_short_circuits(self):
        assert sweep_tags(_Client(_PAGES), []) == {}

    def test_restart_once_on_token_expiry(self):
        client = _Client(_PAGES, raise_first=_client_error("PaginationTokenExpiredException"))
        out = sweep_tags(client, ["s3"])
        assert out["arn:fn:a"] == {"Owner": "sam"}
        assert client._pag.calls == 2  # restarted exactly once

    def test_other_clienterror_propagates(self):
        client = _Client(_PAGES, raise_first=_client_error("ThrottledException"))
        with pytest.raises(ClientError, match="ThrottledException"):
            sweep_tags(client, ["s3"])


class TestResourceTypeFilters:
    def test_collects_sorted_unique_rgta_filters_only(self):
        entries = [
            {"tags": {"source": "rgta", "resource_type_filter": "s3"}},
            {"tags": {"source": "rgta", "resource_type_filter": "lambda:function"}},
            {"tags": {"source": "rgta", "resource_type_filter": "s3"}},  # dup
            {"tags": {"source": "service", "op": "ListRoleTags"}},  # not rgta
            {"natural_key": "X"},  # no tags
        ]
        assert rgta_resource_type_filters(entries) == ["lambda:function", "s3"]
