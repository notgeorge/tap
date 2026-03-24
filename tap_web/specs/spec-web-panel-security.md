# Panel Security Specification

## Philosophy

Panels accept, render, and sometimes edit user-provided data. TAP Web needs one place to define the baseline security contract for panel rendering and panel edit behavior so built-in and future custom panels do not each reinvent form security and sanitization rules.

## Goals

|   |   |   |
| :---: | --- | --- |
| 1. | Consistent | One baseline security contract applies to all panel edit forms |
| 2. | Safe | Panel edit submissions use standard Django security protections |
| 3. | Reusable | Built-in and future custom panels can reference the same security requirements |

## Requirements

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-web-panel-edit-form.sec | [Panel Edit Form Security](#panel-edit-form-security) | Implemented | Platform-level: CSRF middleware + Django Form validation + auto-escaping |
| req-web-panel-render-content.sec | [Panel Content Rendering Security](#panel-content-rendering-security) | Implemented | Platform-level: Django template auto-escaping applies to all panel templates |

### Panel Edit Form Security
----
RID: `req-web-panel-edit-form.sec`
Status: `Implemented`

Panel edit mode accepts user input and must use standard Django form security protections. This requirement standardizes the baseline security behavior for panel edit submissions. These are **platform-level** guarantees: they are satisfied once by the framework and apply to all panel editors automatically. The more general editor-wide contract is being moved to `spec-web-editor.md` under `req-web-editor-form.sec`; this section remains the panel-specific compatibility reference.

#### Status Details
Implemented by the Text Panel editor (first concrete panel type). The security mechanisms are platform-level and apply to all present and future panel editors that follow the standard panel edit flow.

#### Implementation

**CSRF protection** is provided by Django's `CsrfViewMiddleware` in `MIDDLEWARE`. All panel edit form templates must include `{% csrf_token %}`. No per-panel CSRF configuration is required.

**Server-side input sanitization** is implemented via Django Form validation (`form.is_valid()`). Panel edit forms use `forms.CharField(strip=True)` (the Django default) to strip leading/trailing whitespace, enforce `max_length`, and validate field types on the server. Browser-side validation is treated as a UX aid only — forms are always validated server-side before persistence regardless of browser state.

**Untrusted input handling** means submitted values are passed through Django Form `.cleaned_data` before being written to the database. Raw `request.POST` values are not persisted directly.

**Render sanitization** is delegated to `req-web-panel-render-content.sec`. Persisted values flow through Django's template auto-escaping when rendered.

Panel editors should use Django Form classes as the standard server-side validation path. The generic panel edit fallback (raw JSON config editing) is reserved for panels without a registered PanelType and applies the same principle — config is parsed and validated before persistence.

#### Development
This requirement is intentionally generic so built-in and future plugin panels share one baseline security contract. More specialized panel config schema validation can layer on later.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-web-panel-edit-form.sec-1 | CSRF Protection Required | Implemented | Panel edit forms use Django CSRF protection via `CsrfViewMiddleware` in `MIDDLEWARE`. All edit templates include `{% csrf_token %}`. | Platform-level; applies to all panel edit forms. |
| req-web-panel-edit-form.sec-2 | Server-side Input Sanitization Required | Implemented | Panel edit submissions are sanitized server-side via Django Form validation before persistence: whitespace stripped, max_length enforced, types validated. | Implemented in `TextPanelEditForm`; required contract for all panel edit forms. |
| req-web-panel-edit-form.sec-3 | Untrusted Input Handling | Implemented | Panel edit submissions are treated as untrusted input. Values are written to the database only from `form.cleaned_data`, never raw from `request.POST`. | |
| req-web-panel-edit-form.sec-4 | Existing Render Sanitization Applies | Implemented | Values saved through panel edit mode are rendered later using Django's template auto-escaping (`req-web-panel-render-content.sec`). | |

#### Future
Consider adding panel-config-schema validation so editors can validate `config` with more structure than generic form handling alone.

### Panel Content Rendering Security
----
RID: `req-web-panel-render-content.sec`
Status: `Implemented`

Panels render content that may originate from panel configuration, user edits, or searched data. Panel content rendering must default to standard Django escaping and must not treat edited panel content as trusted HTML unless a future requirement explicitly permits it.

#### Status Details
This is a **platform-level** guarantee provided by Django's template engine. Auto-escaping is enabled by default in all Django HTML templates. Panel templates must not use `|safe` or `mark_safe()` on user-provided or panel-config-sourced content.

#### Implementation
- Django template auto-escaping is enabled by default for all `.html` templates.
- Panel content values (`panel.title`, `panel.config.*`, etc.) rendered in templates are automatically HTML-escaped.
- Panel templates must not apply `|safe` or `mark_safe()` to user-sourced content.
- Any future panel type that wants trusted HTML or rich text must define a separate hardened requirement explicitly permitting it.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-web-panel-render-content.sec-1 | Escaping By Default | Implemented | Panel content rendering uses Django template auto-escaping by default. Panel templates must not mark user-sourced values as safe. | Platform-level; verified by Text Panel XSS tests. |
| req-web-panel-render-content.sec-2 | Edited Text Not Trusted HTML | Implemented | Text entered through standard panel editors is not treated as trusted HTML. `config.text` and `title` render as escaped plain text. | Verified in `test_text_panel.py` (`test_html_in_text_is_escaped`). |

#### Future
Define any future rich-text or trusted-HTML panel capability as a separate hardened feature rather than widening the default rendering rule.

## Status Vocabulary

| Status States |  |
| --- | --- |
| Proposed |  |
| Approved for Development | Requirement is accepted and ready to be implemented |
| In Development |  |
| Implemented |  |
| Verified |  |
| Refactoring |  |
| Deprecating |  |
| Deprecated | Not part of the current architecture and should not be implemented |

## RID Format

`req-<application>-<specification>-<feature>-<sub-feature>`

## Requirements Format

`RID: `...``
`Status: `...``

| Sub-Sections | (as needed) |
| --- | --- |
| Status Details |  |
| Implementation |  |
| Development |  |
| Acceptance Criteria |  |
| Future |  |
