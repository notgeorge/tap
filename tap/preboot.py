"""Settings-free pre-boot stage: install package-mode plugins, snapshot the DB.

This module runs in ``docker/entrypoint.sh`` BEFORE Django reads settings — it is
what *generates* ``TAP_PLUGINS`` (which settings then consumes), so it cannot be a
Django app or a ``manage.py`` command. It is deliberately import-safe and
``django``-free (`req-boot-preboot-1`): it reads the boot profile as plain JSON and
talks to the environment directly. ``tap_boot`` owns the profile *contract*
(the schema + the population reader); ``tap/`` *executes* the pre-Django phases —
the Kubernetes ``initContainers`` shape (`req-boot-preboot-2`).

Order (`req-boot-preboot`): resolve the snapshot switch → install the profile's
``install`` plugins (idempotent) → discover their entry points into ``TAP_PLUGINS``
→ static coherence guard → pre-migrate snapshot. Any failure is fatal and aborts
before ``migrate`` runs, leaving the database untouched (`req-boot-preboot-4`).

CLI: ``python -m tap.preboot --profile <id>``. Human/progress output goes to
stderr; the single ``TAP_PLUGINS`` value is printed to stdout (last line) so the
entrypoint can capture it with ``TAP_PLUGINS="$(python -m tap.preboot ...)"``.

Spec: specs/spec-tap-boot-v0.md (`req-boot-preboot`, `req-boot-install-section`,
`req-boot-snapshot`, `req-boot-variable-resolution`, `req-boot-idempotent-3`).
"""

from __future__ import annotations

import argparse
import importlib
import importlib.metadata
import json
import logging
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

logger = logging.getLogger(__name__)

# Repo root = the directory that holds `tap/` and `boot/`. tap/preboot.py lives at
# <root>/tap/preboot.py, so two parents up is the root. Settings-free — no BASE_DIR.
REPO_ROOT = Path(__file__).resolve().parent.parent

# --- Build-baked plugin transition set ---------------------------------------
# Plugins still hardcoded in settings.INSTALLED_APPS (not yet package-mode). The
# static coherence guard treats these as "available" without an `install` entry so
# a legacy profile (samsite) whose population names build-baked plugins still passes.
# This shrinks to empty as plugins migrate to package-mode; `genericom` is NOT here
# (it is the first package-mode plugin). Kept honest against settings by
# tap/tests/test_preboot.py::test_build_baked_matches_installed_apps.
BUILD_BAKED_PLUGIN_SLUGS: frozenset[str] = frozenset(
    {
        # administrivia migrated to package-mode 2026-07-01 (tap_plugin.administrivia).
        "lotr",
        # computing_core migrated to package-mode 2026-07-01 (tap_plugin.computing_core).
        "aws_core",
        # github_core migrated to package-mode 2026-07-01 (tap_plugin.github_core).
        "sigstore_core",
        # roscale migrated to package-mode 2026-07-01 (tap_plugin.roscale).
        "samsite",
        # fedramp_20x_ksi migrated to package-mode 2026-07-01 (first namespaced
        # plugin) — no longer build-baked; installed via the profile `install` section.
        "gryphon_playground",
    }
)

TAP_PLUGINS_ENTRY_POINT_GROUP = "tap.plugins"

# PEP 420 native namespace all package-mode plugins import under: tap_plugin.<slug>
# (singular, to avoid the plural `tap_plugins` management app). The conformance gate
# asserts every plugin's AppConfig lives here. See req-plugin-arch-identity-3.
NAMESPACE_PACKAGE = "tap_plugin"


class PrebootError(Exception):
    """Raised on any fatal pre-boot condition. Aborts the standup before migrate."""


# =============================================================================
# Boot-variable resolution (req-boot-variable-resolution)
# =============================================================================


@dataclass(frozen=True)
class ResolvedVar:
    """A resolved boot variable plus the provenance of the winning value."""

    value: Any
    source: str  # "env" | "profile" | "default"  (flag layer reserved)


def env_var_name(section: str, key: str) -> str:
    """Systematic env mapping ``TAP_BOOT_<SECTION>__<KEY>`` (`req-boot-variable-resolution-2`)."""
    return f"TAP_BOOT_{section.upper()}__{key.upper()}"


def _coerce_bool(raw: str) -> bool:
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def resolve_var(
    section: str,
    key: str,
    *,
    profile_section: dict[str, Any] | None,
    default: Any,
    is_bool: bool = False,
) -> ResolvedVar:
    """Resolve a boot variable by the precedence ladder (`req-boot-variable-resolution-1`).

    Precedence: flag > env > profile > default. The flag layer is reserved for the
    MVP (no CLI-flag override yet), so the effective ladder is env > profile > default.
    Resolve-once: this returns a single effective value plus its source so the caller
    records it (no silent profile divergence, `req-boot-variable-resolution-3`).
    """
    env_name = env_var_name(section, key)
    raw_env = os.environ.get(env_name)
    # An empty/whitespace-only env value means "unset" — docker-compose materializes
    # an unmapped ${VAR:-} as "" in the container, and that must NOT read as a real
    # override (else a prod standup that leaves the var unset would parse "" as False
    # and silently disable the snapshot). Fall through to profile/default.
    if raw_env is not None and raw_env.strip() != "":
        value = _coerce_bool(raw_env) if is_bool else raw_env
        return ResolvedVar(value, "env")

    if profile_section is not None and key in profile_section:
        return ResolvedVar(profile_section[key], "profile")

    return ResolvedVar(default, "default")


# =============================================================================
# Profile reading (plain JSON, settings-free — req-boot-install-section-2)
# =============================================================================


def boot_dir() -> Path:
    return REPO_ROOT / "boot"


def read_profile(profile_id: str) -> dict[str, Any]:
    """Read ``boot/<profile_id>.boot.json`` as plain JSON (no Django, no schema).

    Pre-boot only needs the ``install`` section; it is consumed here as plain JSON
    before settings exist, not by a ``req-boot-sections`` handler (`req-boot-install-section-2`).
    Schema validation is the Django-side ``tap_boot.profile`` reader's job at boot.
    """
    path = boot_dir() / f"{profile_id}.boot.json"
    if not path.is_file():
        raise PrebootError(f"boot profile '{profile_id}' not found at {path}")
    try:
        with open(path, "rb") as fh:
            data: dict[str, Any] = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        raise PrebootError(f"boot profile '{profile_id}' unreadable: {exc}") from exc
    return data


def install_plugin_specs(profile: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the enabled plugin entries from the ``install`` section (order preserved)."""
    install = profile.get("install") or {}
    return [p for p in install.get("plugins", []) if p.get("enabled", False)]


def population_seed_slugs(profile: dict[str, Any]) -> list[str]:
    """Return enabled ``seed-plugin`` slugs from ``population`` (for the coherence guard)."""
    population = profile.get("population") or {}
    return [
        step["plugin"]
        for step in population.get("steps", [])
        if step.get("type") == "seed-plugin" and step.get("enabled", False)
    ]


# =============================================================================
# Plugin install (req-boot-install-section, req-boot-preboot-3 idempotency)
# =============================================================================


def dist_name_for_slug(slug: str) -> str:
    """Distribution name convention: ``tap-plugin-<slug>`` (PEP 503 normalized)."""
    return "tap-plugin-" + slug.replace("_", "-")


def _installed_distribution(dist_name: str) -> importlib.metadata.Distribution | None:
    try:
        return importlib.metadata.distribution(dist_name)
    except importlib.metadata.PackageNotFoundError:
        return None


def _installed_git_rev(dist: importlib.metadata.Distribution) -> str | None:
    """Return the pinned commit id of a VCS install, or None if not a VCS install."""
    raw = dist.read_text("direct_url.json")
    if not raw:
        return None
    info = json.loads(raw)
    vcs = info.get("vcs_info") or {}
    return vcs.get("commit_id") or vcs.get("requested_revision")


def is_satisfied(entry: dict[str, Any]) -> bool:
    """True if the plugin is already installed to the requested source (`req-boot-preboot-3`).

    git: satisfied when the installed VCS commit matches the pinned rev (reboot no-op,
    no re-pull). editable/path: satisfied when the distribution is present — an editable
    install is a live source link, so it needs no reinstall to pick up code changes.
    """
    slug = entry["slug"]
    source = entry["source"]
    dist = _installed_distribution(dist_name_for_slug(slug))
    if dist is None:
        return False
    if source["type"] == "git":
        return bool(_installed_git_rev(dist) == source["rev"])
    return True  # editable / path: presence is enough


def uv_install_args(entry: dict[str, Any]) -> list[str]:
    """Build the ``uv pip install`` argument list for one plugin source."""
    source = entry["source"]
    stype = source["type"]
    if stype == "git":
        spec = f"{dist_name_for_slug(entry['slug'])} @ git+{source['url']}@{source['rev']}"
        return ["uv", "pip", "install", spec]
    if stype == "editable":
        return ["uv", "pip", "install", "--editable", str(REPO_ROOT / source["path"])]
    if stype == "path":
        return ["uv", "pip", "install", str(REPO_ROOT / source["path"])]
    raise PrebootError(f"plugin '{entry['slug']}': unknown source type '{stype}'")


def install_plugins(entries: list[dict[str, Any]]) -> None:
    """Install each enabled plugin, skipping any already satisfied (idempotent)."""
    for entry in entries:
        slug = entry["slug"]
        if is_satisfied(entry):
            logger.info("[a245] pre-boot install: '%s' already satisfied — no-op", slug)
            continue
        args = uv_install_args(entry)
        logger.info("[a83c] pre-boot install: '%s' via %s", slug, " ".join(args))
        result = subprocess.run(args, cwd=str(REPO_ROOT), capture_output=True, text=True)
        if result.returncode != 0:
            logger.error("[b1f5] pre-boot install FAILED for '%s': %s", slug, result.stderr.strip())
            raise PrebootError(f"plugin '{slug}' install failed (exit {result.returncode})")
        logger.info("[c5d5] pre-boot install: '%s' installed", slug)


# =============================================================================
# Entry-point discovery → TAP_PLUGINS (identity check: key == slug)
# =============================================================================


def discover_entry_points() -> dict[str, str]:
    """Map ``tap.plugins`` entry-point name (== slug) → AppConfig dotted path.

    Reads distribution metadata (entry_points.txt) — no package import needed, so a
    just-installed dist is visible in-process without its editable ``.pth`` being active.
    """
    importlib.invalidate_caches()
    discovered: dict[str, str] = {}
    for ep in importlib.metadata.entry_points(group=TAP_PLUGINS_ENTRY_POINT_GROUP):
        discovered[ep.name] = ep.value.replace(":", ".")  # module:attr -> module.attr
    return discovered


def resolve_tap_plugins(entries: list[dict[str, Any]], discovered: dict[str, str]) -> list[str]:
    """Return the AppConfig paths for the installed plugins, enforcing key == slug.

    Identity mismatch (a plugin whose entry-point key does not equal its declared
    slug, or that exposes no ``tap.plugins`` entry point) is fatal (`req-boot-preboot`).
    """
    app_configs: list[str] = []
    for entry in entries:
        slug = entry["slug"]
        if slug not in discovered:
            raise PrebootError(
                f"plugin '{slug}' installed but exposes no '{TAP_PLUGINS_ENTRY_POINT_GROUP}' "
                f"entry point whose key equals the slug (identity mismatch). "
                f"Discovered keys: {sorted(discovered) or '(none)'}"
            )
        app_configs.append(discovered[slug])
    return app_configs


# =============================================================================
# Conformance gate (req-plugin-arch-identity-5): dist == entry-key == namespace == manifest slug
# =============================================================================


def _namespace_segment(app_config_path: str) -> tuple[str, str]:
    """Split a dotted AppConfig path (``tap_plugin.<slug>.apps.<Cls>``) into (top, segment)."""
    parts = app_config_path.split(".")
    top = parts[0] if parts else ""
    segment = parts[1] if len(parts) > 1 else ""
    return top, segment


def _manifest_path_for(entry: dict[str, Any], dist: importlib.metadata.Distribution) -> Path:
    """Locate the plugin's shipped ``tap-plugin.toml`` WITHOUT importing the package.

    A just-installed editable package is not importable in the install process (its
    finder loads at interpreter startup, so ``find_spec`` misses it) — so we read the
    manifest from the filesystem instead. Mode-aware: editable/path installs read the
    source tree; git/index installs read the built copy the distribution shipped into
    site-packages (``dist.locate_file``). Both resolve to ``<pkg>/tap-plugin.toml``.
    """
    slug = entry["slug"]
    source = entry.get("source", {})
    if source.get("type") in ("editable", "path"):
        return REPO_ROOT / source["path"] / NAMESPACE_PACKAGE / slug / "tap-plugin.toml"
    return Path(str(dist.locate_file(f"{NAMESPACE_PACKAGE}/{slug}/tap-plugin.toml")))


def _read_manifest_slug(manifest_path: Path) -> str | None:
    """Read the ``slug`` field from a ``tap-plugin.toml`` at ``manifest_path``, or None."""
    import tomllib

    if not manifest_path.is_file():
        return None
    with open(manifest_path, "rb") as fh:
        loaded: dict[str, Any] = tomllib.load(fh)
    value = loaded.get("slug")
    return value if isinstance(value, str) else None


def _manifest_slug(entry: dict[str, Any], dist: importlib.metadata.Distribution) -> str | None:
    """Return the shipped manifest ``slug`` for an installed plugin — the "actual" side."""
    return _read_manifest_slug(_manifest_path_for(entry, dist))


def conformance_gate(entries: list[dict[str, Any]], discovered: dict[str, str]) -> None:
    """Fail closed unless every plugin's four identities agree (`req-plugin-arch-identity-5`).

    Distribution name (``tap-plugin-<slug>``), entry-point key, import namespace segment
    (``tap_plugin.<slug>``), and manifest ``slug`` must all equal the install slug. Owners
    set the namespace/dist/entry-point in their own package; TAP enforces agreement here —
    the "verify declared matches actual" backstop against typosquat/confusion for
    hand-authored or third-party plugins (the plugin-creation skill emits conformant ones).
    Runs after ``resolve_tap_plugins`` (which already guarantees entry-point key == slug).
    """
    for entry in entries:
        slug = entry["slug"]
        app_config = discovered[slug]

        dist_name = dist_name_for_slug(slug)
        dist = _installed_distribution(dist_name)
        if dist is None:
            raise PrebootError(
                f"conformance gate: plugin '{slug}' has no installed distribution named "
                f"'{dist_name}' — the distribution name must be tap-plugin-<slug>."
            )

        top, segment = _namespace_segment(app_config)
        if top != NAMESPACE_PACKAGE or segment != slug:
            raise PrebootError(
                f"conformance gate: plugin '{slug}' AppConfig '{app_config}' is not under the "
                f"'{NAMESPACE_PACKAGE}.{slug}' namespace (got top='{top}', segment='{segment}'). "
                f"The import namespace segment must equal the slug (req-plugin-arch-identity-3)."
            )

        manifest_slug = _manifest_slug(entry, dist)
        if manifest_slug != slug:
            raise PrebootError(
                f"conformance gate: plugin '{slug}' manifest slug is {manifest_slug!r}, expected "
                f"'{slug}' — tap-plugin.toml slug must equal the install slug / entry-point key."
            )

    logger.info("[be29] pre-boot conformance gate passed: %d plugin(s) identity-verified", len(entries))


# =============================================================================
# Install reconciliation guard (req-boot-install-section-5): declared vs actual
# =============================================================================


def reconciliation_guard(entries: list[dict[str, Any]], discovered: dict[str, str]) -> None:
    """Fail closed if a package-mode plugin is installed on disk but not declared+enabled.

    Reconciles DECLARED (the profile's enabled ``install`` set) against ACTUAL (the
    ``tap.plugins`` entry points discovered in the venv). The *missing* direction —
    declared but not installed — is already fatal in ``resolve_tap_plugins`` (identity
    mismatch). This closes the *other* direction: an installed package-mode distribution
    that NO enabled ``install`` entry declares — a stale install left from a prior profile,
    a plugin the profile ``enabled: false``-d but never got uninstalled, or an undeclared /
    manually-installed plugin. Loading undeclared code at standup is exactly the
    supply-chain surface the declared-vs-actual posture guards, so it fails closed
    (`spec-security-posture` `req-sec-cheap-edges`: over-restriction relaxes cheaply,
    omission retrofits expensively).

    Build-baked plugins are invisible here (they carry no ``tap.plugins`` entry point), so
    the check is scoped to package-mode plugins by construction. In the normal entrypoint
    flow ``uv sync --all-packages`` prunes package-mode dists before pre-boot reinstalls the
    enabled set, so extras are normally zero; a non-empty set means real venv/profile drift.
    """
    install_slugs = {e["slug"] for e in entries}
    extras = sorted(set(discovered) - install_slugs)
    if extras:
        raise PrebootError(
            f"install reconciliation: package-mode plugin(s) {extras} are installed (they expose a "
            f"'{TAP_PLUGINS_ENTRY_POINT_GROUP}' entry point) but are not a declared+enabled `install` "
            f"entry in this profile — undeclared code must not load at standup. Add them to `install`, "
            f"or remove the stale install (uv pip uninstall). "
            f"Declared+enabled: {sorted(install_slugs) or '(none)'}."
        )
    logger.info(
        "[226f] pre-boot install reconciliation passed: %d installed == %d declared package-mode plugin(s)",
        len(discovered),
        len(install_slugs),
    )


# =============================================================================
# Static coherence guard (req-boot-install-section-3)
# =============================================================================


def static_coherence_guard(profile: dict[str, Any], install_slugs: set[str]) -> None:
    """Fail loud (pre-migrate) if a population seed-plugin slug is neither installed nor build-baked."""
    available = install_slugs | BUILD_BAKED_PLUGIN_SLUGS
    missing = [s for s in population_seed_slugs(profile) if s not in available]
    if missing:
        raise PrebootError(
            f"static coherence guard: population seed-plugin(s) {missing} are neither in the "
            f"profile's `install` section nor build-baked. Add them to `install` or fix the typo. "
            f"(installed={sorted(install_slugs) or '(none)'}, build-baked={sorted(BUILD_BAKED_PLUGIN_SLUGS)})"
        )
    logger.info("[ff21] pre-boot static coherence guard passed")


# =============================================================================
# Pre-migrate snapshot (req-boot-snapshot)
# =============================================================================


def snapshot_dir() -> Path:
    return Path(os.environ.get("TAP_SNAPSHOT_DIR", str(REPO_ROOT / ".tap-snapshots")))


def _pg_conn_args() -> tuple[list[str], dict[str, str]]:
    """Parse DATABASE_URL into pg_dump connection flags + a PGPASSWORD env overlay."""
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise PrebootError("snapshot: DATABASE_URL is not set")
    parsed = urlparse(url)
    if not parsed.path or parsed.path == "/":
        raise PrebootError(f"snapshot: DATABASE_URL has no database name: {url}")
    flags = [
        "--host",
        parsed.hostname or "localhost",
        "--port",
        str(parsed.port or 5432),
        "--username",
        unquote(parsed.username or "postgres"),
        "--dbname",
        parsed.path.lstrip("/"),
    ]
    env_overlay = {"PGPASSWORD": unquote(parsed.password)} if parsed.password else {}
    return flags, env_overlay


def take_snapshot() -> Path:
    """Take a verified full-DB snapshot (`pg_dump -Fc`) and return its path.

    Callable primitive (`req-boot-snapshot-6`): a future periodic snapshot system
    reuses this. The snapshot is verified restorable (`pg_restore --list`) before the
    caller proceeds to migrate (`req-boot-snapshot-3`). Restore is a deliberate human
    action, never automatic (`req-boot-snapshot-4`).
    """
    flags, env_overlay = _pg_conn_args()
    out_dir = snapshot_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out_path = out_dir / f"pre-migrate-{stamp}.dump"

    env = {**os.environ, **env_overlay}
    dump = subprocess.run(
        ["pg_dump", "--format=custom", "--file", str(out_path), *flags],
        capture_output=True,
        text=True,
        env=env,
    )
    if dump.returncode != 0:
        raise PrebootError(f"snapshot: pg_dump failed (exit {dump.returncode}): {dump.stderr.strip()}")

    # Verify: file exists, non-empty, and pg_restore can read its table of contents.
    if not out_path.exists() or out_path.stat().st_size == 0:
        raise PrebootError(f"snapshot: pg_dump produced no/empty file at {out_path}")
    listing = subprocess.run(["pg_restore", "--list", str(out_path)], capture_output=True, text=True)
    if listing.returncode != 0:
        raise PrebootError(f"snapshot: verification failed — {out_path} not restorable: {listing.stderr.strip()}")

    logger.info("[409c] pre-boot snapshot written + verified: %s (%d bytes)", out_path, out_path.stat().st_size)
    return out_path


def maybe_snapshot(profile: dict[str, Any]) -> Path | None:
    """Resolve the snapshot switch and take a snapshot unless disabled.

    Switch defaults true on absence (`req-boot-snapshot-2`); a disabled snapshot logs
    loud (WARNING) — a disabled safety net must announce itself.
    """
    install_section = profile.get("install") or {}
    resolved = resolve_var(
        "install",
        "snapshot_before_migrate",
        profile_section=install_section,
        default=True,
        is_bool=True,
    )
    logger.info("[7d43] snapshot_before_migrate = %s (source: %s)", resolved.value, resolved.source)
    if not resolved.value:
        logger.warning(
            "[5d5d] pre-boot snapshot DISABLED (source: %s) — proceeding to migrate with NO restore point",
            resolved.source,
        )
        return None
    return take_snapshot()


# =============================================================================
# Orchestration + CLI
# =============================================================================


def run_preboot(profile_id: str) -> list[str]:
    """Execute the pre-boot stage for a profile; return the resolved TAP_PLUGINS list.

    install → discover (identity) → static coherence guard → snapshot. Any failure
    raises PrebootError; the caller aborts before migrate (`req-boot-preboot-4`).
    """
    logger.info("[43c1] pre-boot stage starting for profile '%s'", profile_id)
    profile = read_profile(profile_id)

    entries = install_plugin_specs(profile)
    install_plugins(entries)

    discovered = discover_entry_points()
    app_configs = resolve_tap_plugins(entries, discovered)
    conformance_gate(entries, discovered)
    reconciliation_guard(entries, discovered)
    install_slugs = {e["slug"] for e in entries}

    static_coherence_guard(profile, install_slugs)

    maybe_snapshot(profile)

    logger.info("[70b4] pre-boot stage complete: %d package-mode plugin(s) -> TAP_PLUGINS", len(app_configs))
    return app_configs


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    parser = argparse.ArgumentParser(prog="tap.preboot", description="TAP settings-free pre-boot stage.")
    parser.add_argument("--profile", required=True, help="boot profile id (boot/<id>.boot.json)")
    args = parser.parse_args(argv)

    try:
        app_configs = run_preboot(args.profile)
    except PrebootError as exc:
        logger.error("[8ed8] pre-boot ABORT: %s", exc)
        return 1

    # stdout carries ONLY the TAP_PLUGINS value (space-separated) for the entrypoint.
    print(" ".join(app_configs))
    return 0


if __name__ == "__main__":
    sys.exit(main())
