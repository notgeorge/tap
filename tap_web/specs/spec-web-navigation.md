# Feature Specification

## Philosophy
- The navigation bar is the classic web-based hamburger menu system of pages and sub-pages.
- Navigation is a first-class node object with title and description.
- `NAV_PAGE` edges connect Navigation to Page nodes in the top-level navigable list.
- Ordering is carried on `NAV_PAGE` edge properties as `order: #` and is enforced by property schema as numeric/decimal.
- `NAV_PAGE` restricts source to Navigation and destination to Page.
- Navigation ordering proceeds from smallest to largest numeric order.
- Sub-pages are represented by decimal ordering (for example `2.2`).
- On page load, navigation rendering collects `NAV_PAGE` links, orders them, and renders a menu where each item navigates to the target page.

## Goals

|   |   |   |
| :---: | --- | --- |
| 1. |  |  |
| 2. |  |  |
| 3. |  |  |

## Requirements

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-web-navigation-base | [Navigation Base](#navigation-base) | Proposed | Navigation node model and `NAV_PAGE`-driven ordering/render behavior |

### Navigation Base
----
RID: `req-web-navigation-base`
Status: `Proposed`

The navigation bar is the classic web-based menu of pages and sub-pages. Navigation is modeled as a first-class node with outbound `NAV_PAGE` edges to Page nodes.

#### Status Details
Initial navigation behavior extracted from page spec and established as the base navigation requirement.

#### Implementation
- `Navigation` is its own node object with title and description.
- `NAV_PAGE` edges connect source `Navigation` to destination `Page`.
- `NAV_PAGE` edge properties include `order` as a numeric decimal value.
- Navigation ordering sorts from smallest to largest `order`.
- Decimal ordering is used for sub-pages (example: `2.2`).
- On page load, navigation rendering collects `NAV_PAGE` links, sorts them by `order`, and renders menu links to target pages.

#### Development
Keep navigation behavior deterministic and data-driven through `NAV_PAGE` edges.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-web-navigation-base-1 | Navigation Node Declared | Proposed | Navigation is modeled as its own node object with title and description. | |
| req-web-navigation-base-2 | NAV_PAGE Edge Direction | Proposed | `NAV_PAGE` restricts source to Navigation and destination to Page. | |
| req-web-navigation-base-3 | Numeric Order Property | Proposed | `NAV_PAGE` requires numeric decimal `order` property used for sorting. | |
| req-web-navigation-base-4 | Deterministic Sort | Proposed | Navigation items are rendered in ascending `order` value. | |
| req-web-navigation-base-5 | Sub-Page Decimal Support | Proposed | Decimal values in `order` represent sub-page placement (example: `2.2`). | |
| req-web-navigation-base-6 | Menu Link Rendering | Proposed | On page load, renderer collects sorted `NAV_PAGE` targets and emits clickable page links. | |

#### Future

## Status Vocabulary

| Status States |  |
| --- | --- |
| Proposed |  |
| Approved for Development |  |
| In Development |  |
| Implemented |  |
| Verified |  |
| Refactoring |  |
| Deprecating |  |
| Deprecated |  |

## RID Format

`req-<application>-<specification>-<feature>-<sub-feature>`

## Requirements Format

`RID: \`...\``  
`Status: \`...\``

| Sub-Sections | (as needed) |
| --- | --- |
| Status Details |  |
| Implementation |  |
| Development |  |
| Acceptance Criteria |  |
| Future |  |
