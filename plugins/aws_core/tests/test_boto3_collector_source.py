"""Source-driver unit tests for the boto3 collector (boto3-free, no DB).

Covers req-aws-collector-source: the generic aws_op driver (paginator vs
single-call, ResponseMetadata strip, items_path extraction) and the
source-dispatch seam (uniform item contract, registered-only custom_fn).
"""

from __future__ import annotations

import pytest

from plugins.aws_core.collectors.boto3_collector.source import (
    CustomFnRegistry,
    SourceError,
    iter_aws_op,
    iter_source,
)


class _FakePaginator:
    def __init__(self, pages):
        self._pages = pages

    def paginate(self, **_kw):
        yield from self._pages


class _FakeClient:
    """Minimal boto3-client stand-in keyed by xform_name'd method names."""

    def __init__(self, *, paginated=None, single=None):
        self._paginated = paginated or {}
        self._single = single or {}

    def can_paginate(self, method):
        return method in self._paginated

    def get_paginator(self, method):
        return _FakePaginator(self._paginated[method])

    def __getattr__(self, name):
        single = self.__dict__.get("_single", {})
        if name in single:
            return lambda: single[name]
        raise AttributeError(name)


class TestIterAwsOp:
    def test_single_call_path(self):
        client = _FakeClient(single={"list_functions": {"Functions": [{"FunctionArn": "a"}, {"FunctionArn": "b"}]}})
        items = list(iter_aws_op(client, "ListFunctions", "Functions[]"))
        assert items == [{"FunctionArn": "a"}, {"FunctionArn": "b"}]

    def test_paginated_path_chains_pages(self):
        client = _FakeClient(
            paginated={"list_roles": [{"Roles": [{"Arn": "r1"}]}, {"Roles": [{"Arn": "r2"}, {"Arn": "r3"}]}]}
        )
        items = list(iter_aws_op(client, "ListRoles", "Roles[]"))
        assert [r["Arn"] for r in items] == ["r1", "r2", "r3"]

    def test_response_metadata_stripped_before_extraction(self):
        client = _FakeClient(
            single={"list_roles": {"Roles": [{"Arn": "r1"}], "ResponseMetadata": {"RequestId": "x"}}}
        )
        items = list(iter_aws_op(client, "ListRoles", "Roles[]"))
        assert items == [{"Arn": "r1"}]
        assert all("ResponseMetadata" not in i for i in items)

    def test_missing_or_empty_items_is_graceful(self):
        client = _FakeClient(single={"list_functions": {}})
        assert list(iter_aws_op(client, "ListFunctions", "Functions[]")) == []

    def test_nested_items_path(self):
        client = _FakeClient(
            single={"list_distributions": {"DistributionList": {"Items": [{"ARN": "d1"}]}}}
        )
        items = list(iter_aws_op(client, "ListDistributions", "DistributionList.Items[]"))
        assert items == [{"ARN": "d1"}]


class TestSourceDispatch:
    def _client_for(self, _service):
        return _FakeClient(single={"list_functions": {"Functions": [{"FunctionArn": "a"}]}})

    def test_aws_op_dispatch(self):
        entry = {
            "service": "lambda",
            "source": {"aws_op": "ListFunctions"},
            "items_path": "Functions[]",
        }
        items = list(iter_source(entry, client_for=self._client_for, custom_fns=CustomFnRegistry()))
        assert items == [{"FunctionArn": "a"}]

    def test_custom_fn_dispatch_same_item_contract(self):
        reg = CustomFnRegistry()
        reg.register("zones", lambda ctx, *, client_for: iter([{"Id": "z1"}, {"Id": "z2"}]))
        entry = {"service": "route53", "source": {"custom_fn": "zones"}, "items_path": "[]"}
        items = list(iter_source(entry, client_for=self._client_for, custom_fns=reg))
        # Same plain-item iterable an aws_op would yield — engine never branches.
        assert items == [{"Id": "z1"}, {"Id": "z2"}]

    def test_unregistered_custom_fn_raises(self):
        entry = {"service": "route53", "source": {"custom_fn": "missing"}, "items_path": "[]"}
        with pytest.raises(SourceError, match="not registered"):
            list(iter_source(entry, client_for=self._client_for, custom_fns=CustomFnRegistry()))

    def test_custom_fn_receives_context(self):
        reg = CustomFnRegistry()
        reg.register("probe", lambda ctx, *, client_for: iter([{"Id": ctx}]))
        entry = {"service": "route53", "source": {"custom_fn": "probe"}, "items_path": "[]"}
        items = list(
            iter_source(entry, client_for=self._client_for, custom_fns=reg, fn_context="REGION-CTX")
        )
        assert items == [{"Id": "REGION-CTX"}]

    def test_custom_fn_receives_client_for(self):
        """Regional custom_fns must receive a region-bound client_for kwarg.

        req-aws-collector-source-5: discovered when the DynamoDB regional
        custom_fn failed with 'You must specify a region.' because the engine
        passed only an unbound session.
        """
        seen: dict[str, object] = {}
        sentinel_client = object()

        def fake_client_for(service):
            seen["asked_for"] = service
            return sentinel_client

        def probe(ctx, *, client_for):
            seen["client"] = client_for("dynamodb")
            yield {"Id": "x"}

        reg = CustomFnRegistry()
        reg.register("probe", probe)
        entry = {"service": "dynamodb", "source": {"custom_fn": "probe"}, "items_path": "[]"}
        list(iter_source(entry, client_for=fake_client_for, custom_fns=reg))
        assert seen["asked_for"] == "dynamodb"
        assert seen["client"] is sentinel_client
