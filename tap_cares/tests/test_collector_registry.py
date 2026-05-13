"""Tests for tap_cares CollectorConfig, CollectorBase, and collector_registry.

Covers:
  req-tap-cares-collector-config
  req-tap-cares-collector-module-class
  req-tap-cares-collector-registry
"""

import dataclasses
from uuid import UUID, uuid4

import pytest
from django.core.exceptions import ImproperlyConfigured

from tap_cares.collectors import CollectorBase, CollectorConfig
from tap_cares.exceptions import (
    CollectorNotFoundError,
    InvalidCollectorRegistryKeyError,
)
from tap_cares.registry import (
    _validate_collector_token,
    collector_registry,
    get_collector,
    register_collector,
)

# ---------------------------------------------------------------------------
# Fixtures + helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def isolate_collector_registry():
    saved = collector_registry.all()
    collector_registry._reset_for_testing()
    yield
    collector_registry._reset_for_testing(saved)


def _make_collector_class(name: str = "Fake", module: str = "tap_cares.tests.fake_collector_module"):
    """Create a CollectorBase subclass with a controllable __module__."""

    class _Fake(CollectorBase):
        def run(self) -> None:
            return None

    _Fake.__name__ = name
    _Fake.__qualname__ = name
    _Fake.__module__ = module
    return _Fake


def _register(key, cls, **kwargs):
    """Test-only wrapper that supplies default name and description.

    register_collector requires name and description per
    req-tap-cares-collector-registration-3, but these registry-mechanics
    tests only care about the sub-grid (ScopedRegistry) side. The on-grid
    upsert silently skips when the DB isn't available (no @pytest.mark.django_db).
    """
    return register_collector(
        key=key,
        cls=cls,
        name=kwargs.pop("name", f"Test collector {key}"),
        description=kwargs.pop("description", "Fixture collector for registry tests."),
        **kwargs,
    )


def _make_config() -> CollectorConfig:
    return CollectorConfig(collector_entity_id=uuid4(), collection_job_entity_id=uuid4())


# ---------------------------------------------------------------------------
# CollectorConfig (req-tap-cares-collector-config)
# ---------------------------------------------------------------------------


class TestCollectorConfig:
    def test_construct_with_uuids(self):
        cid, jid = uuid4(), uuid4()
        cfg = CollectorConfig(collector_entity_id=cid, collection_job_entity_id=jid)
        assert cfg.collector_entity_id == cid
        assert cfg.collection_job_entity_id == jid

    def test_frozen_immutable(self):
        cfg = _make_config()
        with pytest.raises(dataclasses.FrozenInstanceError):
            cfg.collector_entity_id = uuid4()  # type: ignore[misc]

    def test_equality_by_value(self):
        cid, jid = uuid4(), uuid4()
        a = CollectorConfig(collector_entity_id=cid, collection_job_entity_id=jid)
        b = CollectorConfig(collector_entity_id=cid, collection_job_entity_id=jid)
        assert a == b
        assert hash(a) == hash(b)

    def test_json_safe_via_asdict(self):
        cfg = _make_config()
        d = dataclasses.asdict(cfg)
        assert set(d.keys()) == {"collector_entity_id", "collection_job_entity_id"}
        assert all(isinstance(v, UUID) for v in d.values())  # UUIDs are JSON-serializable as str.

    def test_v0_shape_is_two_uuids_only(self):
        # req-tap-cares-collector-config-6 — exactly these two fields, nothing else.
        fields = {f.name for f in dataclasses.fields(CollectorConfig)}
        assert fields == {"collector_entity_id", "collection_job_entity_id"}


# ---------------------------------------------------------------------------
# CollectorBase (req-tap-cares-collector-module-class)
# ---------------------------------------------------------------------------


class TestCollectorBase:
    def test_cannot_instantiate_abstract_base(self):
        with pytest.raises(TypeError, match="abstract"):
            CollectorBase(_make_config())  # type: ignore[abstract]

    def test_subclass_without_run_is_abstract(self):
        class Incomplete(CollectorBase):
            pass

        with pytest.raises(TypeError, match="abstract"):
            Incomplete(_make_config())  # type: ignore[abstract]

    def test_subclass_with_run_instantiates(self):
        Cls = _make_collector_class()
        cfg = _make_config()
        inst = Cls(cfg)
        assert inst.config is cfg

    def test_run_returns_none(self):
        Cls = _make_collector_class()
        inst = Cls(_make_config())
        assert inst.run() is None


# ---------------------------------------------------------------------------
# Validator helper (req-tap-cares-collector-registry-9, -10)
# ---------------------------------------------------------------------------


class TestValidateCollectorToken:
    @pytest.mark.parametrize(
        "value",
        ["a", "Z9", "alpha-beta", "alpha_beta", "a.b.c", "plugins.fedramp_20x_ksi"],
    )
    def test_valid_tokens(self, value):
        _validate_collector_token(value)  # does not raise

    @pytest.mark.parametrize(
        "value",
        ["", "-leading-dash", ".leading-dot", "_leading-underscore", "has space", "has:colon", "has/slash"],
    )
    def test_invalid_tokens(self, value):
        with pytest.raises(InvalidCollectorRegistryKeyError):
            _validate_collector_token(value)

    def test_non_string_rejected(self):
        with pytest.raises(InvalidCollectorRegistryKeyError):
            _validate_collector_token(123)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# register_collector (req-tap-cares-collector-registry, -module-class-6)
# ---------------------------------------------------------------------------


class TestRegisterCollector:
    def test_register_and_get_round_trip(self):
        Cls = _make_collector_class(module="my.plugin")
        _register("alpha", Cls)
        assert get_collector("my.plugin:alpha") is Cls

    def test_scope_inferred_from_module(self):
        Cls = _make_collector_class(module="some.plugin.module")
        _register("inferred", Cls)
        assert "some.plugin.module:inferred" in collector_registry

    def test_scope_can_be_overridden(self):
        Cls = _make_collector_class(module="default.scope")
        _register("ovr", Cls, scope="explicit.scope")
        assert get_collector("explicit.scope:ovr") is Cls

    def test_non_class_rejected(self):
        def not_a_class():
            return None

        with pytest.raises(ImproperlyConfigured, match="CollectorBase"):
            _register("bad", not_a_class, scope="my.scope")  # type: ignore[arg-type]

    def test_non_collector_base_subclass_rejected(self):
        class NotACollector:
            pass

        with pytest.raises(ImproperlyConfigured, match="CollectorBase"):
            _register("bad", NotACollector, scope="my.scope")  # type: ignore[arg-type]

    def test_bad_key_format_rejected(self):
        Cls = _make_collector_class()
        with pytest.raises(InvalidCollectorRegistryKeyError):
            _register("bad key", Cls, scope="ok.scope")

    def test_bad_scope_format_rejected(self):
        Cls = _make_collector_class()
        with pytest.raises(InvalidCollectorRegistryKeyError):
            _register("ok", Cls, scope="bad scope")

    def test_bad_inferred_scope_format_rejected(self):
        Cls = _make_collector_class(module="bad scope from module")
        with pytest.raises(InvalidCollectorRegistryKeyError):
            _register("ok", Cls)

    def test_duplicate_registration_raises(self):
        Cls = _make_collector_class(module="dup.scope")
        _register("dup", Cls)
        with pytest.raises(ImproperlyConfigured, match="already registered"):
            _register("dup", Cls)

    def test_different_scopes_same_key_coexist(self):
        A = _make_collector_class(name="A", module="scope.a")
        B = _make_collector_class(name="B", module="scope.b")
        _register("shared", A)
        _register("shared", B)
        assert get_collector("scope.a:shared") is A
        assert get_collector("scope.b:shared") is B

    def test_bad_format_register_leaves_registry_unchanged(self):
        Cls = _make_collector_class()
        try:
            _register("bad key", Cls, scope="ok.scope")
        except InvalidCollectorRegistryKeyError:
            pass
        assert collector_registry.keys() == []


# ---------------------------------------------------------------------------
# get_collector (req-tap-cares-collector-registry, exceptions)
# ---------------------------------------------------------------------------


class TestGetCollector:
    def test_missing_key_raises_collector_not_found(self):
        with pytest.raises(CollectorNotFoundError, match="missing"):
            get_collector("some.scope:missing")

    def test_error_message_lists_registered_keys(self):
        _register("present", _make_collector_class(module="some.scope"))
        with pytest.raises(CollectorNotFoundError) as exc_info:
            get_collector("some.scope:absent")
        assert "some.scope:present" in str(exc_info.value)

    def test_malformed_key_raises_invalid_token(self):
        with pytest.raises(InvalidCollectorRegistryKeyError):
            get_collector("bad scope:key")
        with pytest.raises(InvalidCollectorRegistryKeyError):
            get_collector("ok.scope:bad key")


# ---------------------------------------------------------------------------
# Registry visibility (req-tap-cares-collector-registry-2, meta-registry surface)
# ---------------------------------------------------------------------------


class TestRegistryVisibility:
    def test_collector_registry_in_meta_registry(self):
        from tap_grid.registry import meta_registry

        assert "collector" in meta_registry

    def test_collector_registry_separate_from_search(self):
        from tap_grid.registry import search_runner_registry

        assert collector_registry is not search_runner_registry
