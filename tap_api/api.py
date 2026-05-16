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


def discover_plugin_routers() -> None:
    """Mount API routers from all TapPluginConfig subclasses.

    Plugins override get_api_router() to expose a ninja.Router.
    Mounted at /plugins/<label>/... by tap_api.
    """
    from tap_plugins.base import TapPluginConfig

    for app_config in apps.get_app_configs():
        if not isinstance(app_config, TapPluginConfig):
            continue

        router = app_config.get_api_router()
        if router is None:
            continue

        prefix = f"/plugins/{app_config.label}/"
        tag = str(app_config.verbose_name) if app_config.verbose_name else app_config.label
        logger.info("[acf9] Mounting plugin API router: %s -> %s", app_config.label, prefix)
        api.add_router(prefix, router, tags=[tag], auth=session_auth)
