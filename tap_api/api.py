"""TAP API — NinjaAPI instance, core routers, plugin router discovery."""

import logging
from typing import Any

from django.apps import apps
from django.http import HttpRequest
from ninja import NinjaAPI

from tap_api.auth import session_auth
from tap_api.routers.edges import router as edges_router
from tap_api.routers.entities import router as entities_router
from tap_api.routers.entity_types import router as entity_types_router
from tap_api.routers.gryphon import router as gryphon_router
from tap_api.routers.searches import router as searches_router

logger = logging.getLogger(__name__)

api = NinjaAPI(
    title="TAP API",
    version="1",
    urls_namespace="tap-api",
)

# Core routers — auth applied at mount time so TestClient(router) bypasses auth
api.add_router("/entities/", entities_router, tags=["Entities"], auth=session_auth)
api.add_router("/edges/", edges_router, tags=["Edges"], auth=session_auth)
api.add_router("/entity-types/", entity_types_router, tags=["Entity Types"], auth=session_auth)
api.add_router("/searches/", searches_router, tags=["Searches"], auth=session_auth)
api.add_router("/gryphon/", gryphon_router, tags=["Gryphon"], auth=session_auth)


@api.get("/", auth=None, tags=["Meta"])
def api_root(request: HttpRequest) -> dict[str, Any]:
    """Version info for this API."""
    return {"version": "1", "latest": True}


def resolve_plugin_mounts(plugin_configs: Any) -> list[tuple[str, Any, str]]:
    """Resolve (mount_prefix, router, tag) for each plugin exposing a router.

    Pure resolution + collision guard, separated from the live mounting so the
    dedup invariant is unit-testable without the Django app registry. Each plugin
    maps to a unique mount prefix `/plugins/<label>/`. Two plugins resolving to
    the same prefix is a hard error — silently overwriting one router with
    another is exactly the failure mode we refuse to allow.

    Args:
        plugin_configs: Iterable of TapPluginConfig-like objects exposing
            `label`, `verbose_name`, and `get_api_router()`.

    Returns:
        A list of (prefix, router, tag) tuples for plugins that expose a router.

    Raises:
        ImproperlyConfigured: If two plugins resolve to the same mount prefix.
    """
    from django.core.exceptions import ImproperlyConfigured

    mounts: list[tuple[str, Any, str]] = []
    seen_prefixes: dict[str, str] = {}
    for app_config in plugin_configs:
        router = app_config.get_api_router()
        if router is None:
            continue

        prefix = f"/plugins/{app_config.label}/"
        if prefix in seen_prefixes:
            logger.error(
                "[e0aa] Duplicate plugin API router mount prefix %s: labels %s and %s collide",
                prefix,
                seen_prefixes[prefix],
                app_config.label,
            )
            raise ImproperlyConfigured(
                f"Duplicate plugin API router mount prefix {prefix!r}: plugin labels "
                f"{seen_prefixes[prefix]!r} and {app_config.label!r} both resolve to it. "
                "Plugin labels must be unique and map to a unique mount prefix; refusing "
                "to silently overwrite a previously-mounted router."
            )
        seen_prefixes[prefix] = app_config.label

        tag = str(app_config.verbose_name) if app_config.verbose_name else app_config.label
        mounts.append((prefix, router, tag))
    return mounts


def discover_plugin_routers() -> None:
    """Mount API routers from all TapPluginConfig subclasses.

    Plugins override get_api_router() to expose a ninja.Router.
    Mounted at /plugins/<label>/... by tap_api. A duplicate mount prefix raises
    ImproperlyConfigured rather than silently overwriting (see resolve_plugin_mounts).
    """
    from tap_plugins.base import TapPluginConfig

    plugin_configs = [cfg for cfg in apps.get_app_configs() if isinstance(cfg, TapPluginConfig)]
    for prefix, router, tag in resolve_plugin_mounts(plugin_configs):
        logger.info("[acf9] Mounting plugin API router: %s -> %s", prefix, tag)
        api.add_router(prefix, router, tags=[tag], auth=session_auth)
