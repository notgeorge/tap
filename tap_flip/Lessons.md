# tap_flip Lessons Learned

Decision log and implementation insights for FLIP (Field-Level Information Provenance).

---

## Summary

### What is FLIP?

FLIP provides provenance tracking for TAP's graph data. It answers "who changed what, when, and why" for any domain model in the system. FLIP is designed as an opt-in system where models explicitly declare which provenance features they need.

### Goals

1. **Auditability**: Track all changes to domain models with user attribution
2. **Batch Correlation**: Group related changes into logical batches for rollback and review
3. **Flexibility**: Allow models to opt into provenance features as needed
4. **Swappability**: Abstract the history backend behind a service layer for future changes
5. **Compliance Readiness**: Support Rampart's continuous compliance requirements

### Key Architectural Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| History backend | django-simple-history | Mature, well-maintained, handles migrations automatically |
| Feature activation | Opt-in via `FLIP_CONFIG` class attribute | Avoids overhead for models that don't need tracking |
| User attribution | ContextVars with explicit override | Balances convenience (implicit context) with precision (explicit params) |
| Batch model type | Hybrid (Batch is Entity, BatchEvent is standalone) | Batch participates in graph; events are internal bookkeeping |
| batch_id field | On BaseModel, blank by default | Ready for Phase 2 without requiring migration changes |
| History registration | Explicit `HistoricalRecords` on model | Django migrations require class-level definition |

### Implementation Phases

| Phase | Scope | Status |
|-------|-------|--------|
| Phase 1 | FLIP_CONFIG pattern, django-simple-history integration, history service layer | Complete |
| Phase 2 | Batch and BatchEvent models, batch_id population, batch lifecycle, signals | Complete |
| Phase 3 | Consensus policies, multi-actor approval workflows | Future |

### Files Created (Phase 1)

```
tap_flip/
├── config.py              # FLIP_CONFIG defaults and merging
├── history/
│   ├── __init__.py        # Package exports
│   ├── context.py         # ContextVars for user/batch_id
│   └── service.py         # History query adapter layer
└── tests/
    ├── test_config.py
    ├── test_history_context.py
    ├── test_history_service.py
    └── test_integration.py
```

### Files Modified (Phase 1)

- `pyproject.toml` - Added django-simple-history dependency
- `tap/settings.py` - Added simple_history to INSTALLED_APPS
- `tap_grid/models.py` - Added batch_id field to BaseModel
- `tap_plugins/core_examples/models.py` - Added FLIP_CONFIG and HistoricalRecords to Concept

### Files Created (Phase 2)

```
tap_flip/
├── models.py              # Batch and BatchEvent models
├── admin.py               # Admin for Batch and BatchEvent
├── apps.py                # Updated with signal connection
├── batch/
│   ├── __init__.py        # Package exports
│   ├── service.py         # Batch lifecycle API
│   └── signals.py         # pre_save, post_save, post_delete handlers
└── tests/
    ├── test_batch_models.py
    ├── test_batch_service.py
    └── test_batch_signals.py
```

### Files Modified (Phase 2)

- `tap_flip/apps.py` - Import signals in `ready()` to connect them
- `tap_plugins/core_examples/models.py` - Added `batch: {enabled: True}` to Concept's FLIP_CONFIG

---

## Phase 1: FLIP_CONFIG + History Tracking

### django-simple-history Requires Explicit Class-Level Registration

**Problem**: Attempted to dynamically register `HistoricalRecords` in `BaseModel.__init_subclass__()` to keep models DRY. This worked at runtime but failed to generate migrations.

**Approaches tried**:
1. Dynamic `cls.history = HistoricalRecords()` in `__init_subclass__` - No migrations generated
2. `simple_history.register(cls)` in `__init_subclass__` - HistoricalBaseModel error
3. `simple_history.register(cls)` in `AppConfig.ready()` - No migrations generated

**Solution**: Each model needing history must explicitly declare:
```python
from simple_history.models import HistoricalRecords
from tap_flip.history.context import get_history_user

class MyModel(BaseModel):
    FLIP_CONFIG = {"history": {"enabled": True}}
    history = HistoricalRecords(get_user=get_history_user)
```

**Rationale**: Django's migration system inspects model classes at import time. Dynamic registration happens too late for `makemigrations` to detect the history manager. The explicit declaration is more verbose but ensures migrations are created correctly.

**FLIP_CONFIG still valuable**: Even with explicit history registration, the config pattern provides:
- Centralized feature flag checking via `is_history_enabled()`
- Future extensibility for depth limits, batch tracking, consensus
- Consistent pattern across all FLIP features

---

### get_user Callback Signature for django-simple-history

**Problem**: `get_history_user()` failed with "got unexpected keyword argument 'instance'".

**Cause**: django-simple-history passes `instance` and other kwargs to the `get_user` callback.

**Solution**: Accept and ignore these parameters:
```python
def get_history_user(instance: object = None, **kwargs: object) -> User | None:
    return _history_user.get()
```

---

### CharField vs NullBooleanField for batch_id

**Problem**: Initial implementation used `null=True` for `batch_id` CharField, triggering DJ001 linting error.

**Django convention**: For string fields, use `blank=True, default=""` instead of `null=True`. This avoids two representations of "no value" (NULL and empty string).

**Solution**:
```python
batch_id = models.CharField(
    max_length=36,
    blank=True,
    default="",
    db_index=True,
)
```

---

### Mypy and Third-Party Packages Without Stubs

**Problem**: `simple_history` lacks type stubs, causing mypy import errors.

**Solution**: Add override in `pyproject.toml`:
```toml
[[tool.mypy.overrides]]
module = ["simple_history", "simple_history.*"]
ignore_missing_imports = true
```

For dynamic attributes like `model_instance.history`, use inline ignore:
```python
return model_instance.history.all()  # type: ignore[attr-defined]
```

---

### ContextVars for Request-Scoped Attribution

**Pattern**: Use `contextvars` for implicit context that would otherwise require threading through every function signature.

**Implementation**:
```python
_history_user: contextvars.ContextVar[User | None] = contextvars.ContextVar(
    "history_user", default=None
)
```

**Usage in middleware/views**:
```python
from tap_flip.history import set_history_user
set_history_user(request.user)
```

**Design decision**: Explicit parameters in service calls take precedence over context. This allows both convenience (context fallback) and precision (explicit override) depending on the call site's needs.

---

## Phase 2: Batch Tracking System

### Signals vs Explicit Service Calls

**Decision**: Use Django signals for batch event recording.

**Initial hesitation**: CLAUDE.md says "use Django signals sparingly."

**Why signals were the right choice**:
1. **Matches django-simple-history pattern** - Same approach we already use for history tracking
2. **Cross-cutting audit concern** - Captures ALL changes, not just service layer calls
3. **Safety net** - Admin, shell, management commands, direct ORM all get tracked
4. **Context is already implicit** - Signal just reads `get_batch_id()` from contextvars
5. **No-op when disabled** - If no batch context or batch tracking disabled, signals do nothing

**Implementation**:
- `pre_save`: Populates `batch_id` field on the model instance
- `post_save`: Records BatchEvent after save (create or update)
- `post_delete`: Records BatchEvent for deletions

---

### Batch Model Disables Self-Tracking

**Problem**: If Batch has batch tracking enabled, creating a batch would trigger the signal, which would try to record a BatchEvent, which would look for a batch... infinite recursion.

**Solution**: Batch's FLIP_CONFIG explicitly disables batch tracking:
```python
class Batch(BaseModel):
    FLIP_CONFIG = {
        "history": {"enabled": True},   # Track batch metadata changes
        "batch": {"enabled": False},    # Prevent self-reference
    }
```

---

### BatchEvent as Standalone Model

**Decision**: BatchEvent does NOT extend BaseModel (is not an Entity).

**Rationale**:
- Events are internal bookkeeping, not graph participants
- Events are immutable after creation (append-only log)
- Simpler schema without Entity overhead
- CASCADE delete when parent Batch is deleted

---

### Delta Storage NOT in BatchEvent

**Decision**: BatchEvent records correlation only (what batch), not reconstruction (what changed).

**Rationale**:
- django-simple-history already captures full snapshots per change
- Duplicating deltas creates two sources of truth
- BatchEvent's job is "which batch was this in", not "what exactly changed"

---

### Signal Registration in AppConfig.ready()

**Pattern**: Import signals module in `AppConfig.ready()` to connect handlers:
```python
class TapFlipConfig(AppConfig):
    def ready(self) -> None:
        import tap_flip.batch.signals  # noqa: F401
```

This ensures signals are connected after Django's app registry is fully populated.

---

## Future Considerations

### Phase 3: Consensus
- Edge-based "emerged view" per object
- Multi-actor approval workflows
- Policy configuration in FLIP_CONFIG

### Potential Improvements
- History pruning based on `depth_revisions` and `depth_days` config
- Middleware to auto-set history user and batch context
- Batch rollback functionality (undo all changes in a batch)
- Batch analytics (count of creates/updates/deletes per batch)
