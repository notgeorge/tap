"""OSCAL document-type constants and vendored-schema paths used by parser and validator."""

from pathlib import Path

OSCAL_VERSION = "1.1.2"

_VENDOR_ROOT = Path(__file__).resolve().parent / "vendor" / "nist" / "oscal" / OSCAL_VERSION / "schemas"

# Root-key → (short-slug, schema-filename) for every OSCAL document type
# the vendored schemas cover. The root key is the single top-level property
# in a valid OSCAL JSON document (e.g. {"system-security-plan": {...}}).
OSCAL_DOCUMENT_TYPES: dict[str, tuple[str, str]] = {
    "catalog": ("catalog", "oscal_catalog_schema.json"),
    "profile": ("profile", "oscal_profile_schema.json"),
    "component-definition": ("component", "oscal_component_schema.json"),
    "system-security-plan": ("ssp", "oscal_ssp_schema.json"),
    "assessment-plan": ("ap", "oscal_assessment-plan_schema.json"),
    "assessment-results": ("ar", "oscal_assessment-results_schema.json"),
    "plan-of-action-and-milestones": ("poam", "oscal_poam_schema.json"),
}

OSCAL_ROOT_KEYS: frozenset[str] = frozenset(OSCAL_DOCUMENT_TYPES.keys())


def schema_path_for(root_key: str) -> Path | None:
    entry = OSCAL_DOCUMENT_TYPES.get(root_key)
    if entry is None:
        return None
    return _VENDOR_ROOT / entry[1]


def document_type_for(root_key: str) -> str | None:
    entry = OSCAL_DOCUMENT_TYPES.get(root_key)
    if entry is None:
        return None
    return entry[0]


# Friendly control-family labels for SSP rendering. OSCAL control IDs are
# kebab-case "<family>-<number>" (e.g. "ac-2"); the family prefix maps to
# a NIST 800-53 family label. Unknown prefixes fall back to the bare prefix.
NIST_800_53_FAMILIES: dict[str, str] = {
    "ac": "AC — Access Control",
    "at": "AT — Awareness and Training",
    "au": "AU — Audit and Accountability",
    "ca": "CA — Assessment, Authorization, and Monitoring",
    "cm": "CM — Configuration Management",
    "cp": "CP — Contingency Planning",
    "ia": "IA — Identification and Authentication",
    "ir": "IR — Incident Response",
    "ma": "MA — Maintenance",
    "mp": "MP — Media Protection",
    "pe": "PE — Physical and Environmental Protection",
    "pl": "PL — Planning",
    "pm": "PM — Program Management",
    "ps": "PS — Personnel Security",
    "pt": "PT — Personally Identifiable Information Processing and Transparency",
    "ra": "RA — Risk Assessment",
    "sa": "SA — System and Services Acquisition",
    "sc": "SC — System and Communications Protection",
    "si": "SI — System and Information Integrity",
    "sr": "SR — Supply Chain Risk Management",
}


def control_family_label(control_id: str) -> str:
    if not control_id or "-" not in control_id:
        return control_id or ""
    prefix = control_id.split("-", 1)[0].lower()
    return NIST_800_53_FAMILIES.get(prefix, prefix.upper())
