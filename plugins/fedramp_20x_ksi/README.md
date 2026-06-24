# tap-plugin-fedramp-20x-ksi

TAP plugin modeling the [FedRAMP 20x Key Security Indicators](https://www.fedramp.gov/docs/20x/key-security-indicators/) catalog as graph nodes — themes and individual indicators — so evidence, observations, and compliance posture can attach to them in TAP.

## What's in the catalog

**Themes** — top-level groupings of related security outcomes (10 as of the `2026.0.1.1-wip-preview` consolidated rules release).

| Code | Theme |
| --- | --- |
| KSI-CMT | Change Management |
| KSI-CNA | Cloud Native Architecture |
| KSI-CED | Cybersecurity Education |
| KSI-IAM | Identity and Access Management |
| KSI-INR | Incident Response |
| KSI-MLA | Monitoring, Logging, and Auditing |
| KSI-PIY | Policy and Inventory |
| KSI-RPL | Recovery Planning |
| KSI-SVC | Service Configuration |
| KSI-SCR | Supply Chain Risk |

**Indicators** — individual measurable security outcomes within a theme (e.g. `KSI-IAM-MFA`). Each indicator carries a requirement statement, NIST 800-53 control references, source metadata (changelog, terms, external references), applicable FedRAMP Certification Classes, and lifecycle status (`draft`/`published`/`deprecated`).

**FedRAMP Certification Classes** — values `a`/`b`/`c`/`d` replace the legacy Low/Moderate/High impact-baseline system. Class A is pilot-grade (replaces "FedRAMP Ready"); B roughly maps to Low/Li-SaaS; C to Moderate; D to High (requires agency sponsor).

The plugin source of truth is the FedRAMP-published machine-readable [consolidated rules](https://github.com/FedRAMP/rules/blob/main/fedramp-consolidated-rules.json) (`KSI` section). `KSI-ABF` (Authorization by FedRAMP) appears in the FedRAMP docs site but is not part of the machine-readable KSI catalog and is out of scope for this plugin.

## TAP surfaces

**Models:** `ksi_theme`, `ksi_indicator`

**Edges:** `CONTAINS_INDICATOR` (theme → indicator)

**Default dimensions:** `{"compliance": "fedramp-20x"}` on every node and edge

## Installation

Add as a submodule from the TAP repo root:

```bash
git submodule add https://github.com/notgeorge/tap-plugin-fedramp-20x-ksi.git plugins/fedramp_20x_ksi
```

Then add `"plugins.fedramp_20x_ksi"` to `INSTALLED_APPS` and run migrations:

```bash
docker compose exec web uv run python manage.py migrate
```

## Validation

From the TAP repo root, structure-level validation (runs without Django):

```bash
docker compose exec web uv run python -m tap_plugins.validate_plugin plugins/fedramp_20x_ksi --strict
```

Loads and runs validation (requires the plugin in `INSTALLED_APPS` and migrations applied):

```bash
docker compose exec web uv run python manage.py validate_plugin plugins/fedramp_20x_ksi --level runs
```

## Catalog distribution

The plugin ships one initial seed file, `grift/ksi-seed.grift.json`, containing a current-time snapshot of themes and indicators. Ongoing catalog updates land via the **runtime KSI collector** (`plugins.fedramp_20x_ksi.collectors.ksi_catalog.KSICollector`), which fetches the upstream consolidated rules JSON, applies safety checks, diffs against grid state, and submits a GRIFT batch for changes only. The collector is registered with `tap_cares` and can be enqueued like any other collector.

The on-grid `Collector` node is materialized by `reconcile_collector_nodes()` (run by the boot orchestrator after plugin load); `register_collector(...)` in `Fedramp20xKsiConfig.ready()` only registers the runner read-only. No manual seeding required. To enqueue a run:

```python
from tap_cares.models import Collector
from tap_cares.services import run_collection

col = Collector.objects.get(
    collector_registry="plugins.fedramp_20x_ksi.collectors.ksi_catalog:ksi-catalog",
)
run_collection(col)
```

See `specs/spec-fedramp-20x-ksi-collector.md` for the collector design, pinned source schema, safety checks (structural caps, character class, denylist, mass-deletion threshold), and the `tap.fedramp_20x_ksi.collection-v0` batch description format.

## Specification

See [`specs/spec-fedramp-20x-ksi-v0.md`](specs/spec-fedramp-20x-ksi-v0.md) for plugin-level requirements (models, edges, dimensions, icon contract) and [`specs/spec-fedramp-20x-ksi-collector.md`](specs/spec-fedramp-20x-ksi-collector.md) for the runtime collector.
