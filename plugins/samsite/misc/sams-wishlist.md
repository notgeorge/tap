# Sam's Wishlist — Compliance Pages, History, and Our Own Checks

Drafted 2026-05-23. The set of pages, panels, history surfaces, and grid-side
compliance checks worth building once the samsite compliance subgraph is on
the grid (KSI signal + VDR + OSCAL/IIW artifacts, all live-verified). This
is a wishlist, not a spec — to be revisited and ordered before any of it is
built.

## Framing — the core insight

We now have **three views of the same system** on the grid:

- **Attested** — Sam's KSI signal + OSCAL SSP/POA&M (what he says the system is).
- **Observed** — the boto3 collector's AWS inventory (what the cloud actually shows).
- **Evaluated** — the VDR report + (eventually) our own grid-side checks.

Sam can ship attestations. Sam can run validations. Sam *cannot* join these
three views — his artifacts are static documents. **TAP's marquee move is
joining them.** Every page worth building should be a join Sam couldn't write
himself. Anything we build that's just "Sam's OSCAL in HTML" is a waste of
the grid.

## Pages, in priority order

### 1. The Joined Inventory (the killer page)

What's attested vs what's observed. Three columns:

- `ksi_component`s we have, with no matching AWS node — **phantom** (declared but not deployed)
- AWS nodes with no matching `ksi_component` — **shadow** (deployed but not declared)
- Matched pairs, with a one-row drift summary — does the attested type match the observed type? does the security_category make sense given the actual config?

This is the panel that makes a compliance lead's stomach drop or relax
instantly. It's also the panel Sam *literally cannot build*, because he
doesn't have the observed side. Build this first; it carries any demo.

**Build dependency:** needs the `aws_core` ↔ `ksi_component` cross-edge that
was named a v0 non-goal in `spec-fedramp-20x-ksi-compliance-artifacts-v0.md`.
**That non-goal should move.** It's the load-bearing edge for the most
valuable view. A focused day of work: a resolver that matches
`ksi_component.type` + `native_id` against the boto3 collector's nodes
(`object_store` ↔ `aws_s3_bucket` by bucket name, `function` ↔ `aws_lambda`
by function name, `cdn_distribution` ↔ `aws_cloudfront_distribution` by id,
etc.).

### 2. Component Detail — Sam's own marquee query, lit up

Pick one `ksi_component`. Show:
- The validations that evaluated it (one-hop over `EVALUATES_COMPONENT` — the join Sam's own schema is built around), pass/fail status per validation.
- The matched AWS resource (via #1's cross-edge).
- VDR findings affecting this component (via `AFFECTS_RESOURCE` when resolvable).
- A history panel — how this component's fields drifted across emissions.

Sam designed his schema around the validation/component join; we make it a
clickable surface instead of a JSON array lookup.

### 3. VDR Posture

- A heatmap on PAIN × (IRV, LEV), with KEV-flagged findings in red.
- An SLA timeline (`remediation_due_at` − `now`).
- A risk-accepted-with-POA&M-ref table.

The data's already typed and queryable; this is half a Gryphon query and
half a panel. Sam *has* this in VDR-the-document; we make it live, sortable,
drillable.

### 4. Provenance & Trust

- Signed-by URI, verified_at, the Sigstore details.
- The workflow / commit / run that produced the emission.
- Sigstore link to the Rekor entry (when we extract the log index).
- Ownership: system_owner, application_owner, operator_contact.
- Disclosure: authorization_status, fedramp_certified.

Small but high-credibility — "this attestation chains to a specific CI run
signed by a known workflow." The "show me the receipts" page.

### 5. Compliance Artifact Library

OSCAL SSP / POA&M / IIW viewer. Honest deliverable but low marginal value
over Sam's own docs site — it's "we have the documents." Build it last, or
skip if time is tight.

**Deliberately NOT building** a "compliance overview" KPI dashboard first.
That's the consultant's instinct (numbers in a row). The joined-inventory +
component-detail combo is more powerful and more honest about what TAP
uniquely does.

## Where history actually pays

TAP's per-model history (`django-simple-history`) is on every `BaseModel`.
Every emission re-upserts the same `ksi_component` (dedup by `component_id`,
per the spec), so each component has a **timeline of versions**. That
unlocks things Sam structurally can't get from emission-as-document:

- **Component drift timeline.** "This S3 bucket's `security_category.confidentiality` changed from HIGH to MODERATE on 2026-04-12 — what happened?" A history table on the component-detail page.
- **Finding lifecycle.** A `vdr_finding`'s `current_disposition` changes `open` → `risk-accepted` over emissions. Plot the lifecycle: when first_detected, when accepted, by which POA&M reference. Sam has this implicit in the VDR ledger; we make it traversable.
- **Attestation cadence health.** "Sam claims weekly attestation; the emission timeline shows last 14 weekly + one 22-day gap two months ago." A panel that flags cadence drift.
- **"What changed since the auditor last looked?"** Pick a date, diff every component and finding's state then vs now. The panel an auditor *actually* wants and could never previously have.

**Identity matters here.** `ksi_signal` and `vdr_report` are per-emission
(different `signal_id` → different node, accumulating). `ksi_component` and
`vdr_finding` dedup across emissions (stable `component_id` / `tracking_id`)
— those are the ones whose *history rows* tell the drift story. Build the
history panels on the things that dedup; treat the per-emission nodes as the
timeline scaffold.

## Our own compliance checks — Gryphon queries as evidence

The "trust but verify" play. Sam's documents say things; the grid says
things; we check.

**v0 shape — start as `Search` entities.** A compliance check is a Gryphon
search with an expected predicate (`count == 0`, `every row has
signature_verified=True`, etc.). Stash them as grift seeds in the
`fedramp_20x_ksi` plugin. Run on demand (a "Run all checks" page) and on
each KSI signal collection. A check that fails materializes a `finding`
(model already exists) linked by `COVERS_COMPLIANCE_FINDING` back to the relevant
`ksi_component`s. A check that passes materializes (or refreshes) an
`evidence` node (also already in the model catalog). **No new model needed
for v0** — we're using vocabulary that's already there.

### Concrete checks to seed first

Drawn from the data we have on the grid right now, runnable with bare-MATCH
+ envelope-paths:

1. **No undeclared S3 buckets.** `MATCH (b:aws_s3_bucket) WHERE NOT EXISTS (ksi_component with native_id = b.bucket_name)` — flag shadow buckets. (Needs the cross-edge from page #1 to be precise; without it, fuzzy match on name.)
2. **No public-readable buckets the KSI signal doesn't disclose.** `MATCH (b:aws_s3_bucket) WHERE b.public_access_block.* IS NOT all-blocked` — flag, intersect with KSI inventory.
3. **Sam's claimed signing identity matches reality.** `MATCH (s:ksi_signal) WHERE s.signed_by != s.provenance_builder_id` — drift between what the workflow URI says and what the cert says it signed.
4. **No N4/N5 internet-reachable findings past SLA.** `MATCH (f:vdr_finding) WHERE f.pain IN ["N4","N5"] AND f.internet_reachable AND f.current_disposition = "open" AND f.remediation_due_at < now()` — one Gryphon query, runs against current grid state.
5. **Every CloudFront distribution has OAC.** `MATCH (d:aws_cloudfront_distribution) WHERE d.configuration.origin_access_control IS empty` — the earlier OAC collection gap is now plug-and-go.
6. **EventBridge rule → Lambda invocations have least-privilege roles.** Walk the `INVOKES` edge to the Lambda, walk its IAM role, check the policy. Multi-hop. The kind of thing Sam can't easily write.
7. **VDR-attested source tools all reporting.** `MATCH (f:vdr_finding)` → DISTINCT source → assert `{opa, checkov, tfsec, dependabot} ⊆ observed`. If Dependabot disappeared, we'd know.
8. **Sigstore-verified.** All `signature_verified = True`. Trivial; high signal as a "system green" boolean.

**v1, once there's a demand signal:** a dedicated `compliance_check` model
(query + expected predicate + schedule). For now, `Search` + a thin "run
this and evaluate" wrapper. Don't pre-build the model.

## What we add that Sam isn't thinking about

Six, in order of bet-strength:

1. **Shadow infrastructure detection.** Every AWS node with no matching ksi_component is a thing Sam attested doesn't exist but does. Pure win — Sam structurally can't see this from his side.
2. **Cross-tool intersection findings.** Dependabot finds a CVE in package P; KSI inventory has P with information_flow showing it touches user data; AFFECTS_RESOURCE links them. The *exposure-amplified* subset of findings. Higher-priority than the raw VDR list.
3. **Multi-emission diff.** Pick two emissions, show every component/validation/finding that changed. The "what's new since last week's attestation" view. Trivially queryable once we have history; impossible to write against static OSCAL.
4. **Live re-validation.** Sam's signal said pass at CI time. The grid is live now. Re-run the equivalent of his validation policies against current observed state and compare. Worth doing once the grid has a few more days of history.
5. **Portfolio aggregation seam.** Sam's KSI signal explicitly aims at portfolio reasoning across CSPs. The grid is the natural place this lives. *Not building for the demo* — but worth naming as a future seam (a second `system_id` lands and the same pages just work).
6. **Forensic provenance walks.** From any finding → walk to component → AWS resource → IAM role → policy → permissions. The incident-response trail. High-credibility, lower-frequency-use.

## Recommended demo sequence (June 1)

1. **The `aws_core` ↔ `ksi_component` cross-edge** — lift it out of the non-goal list. It's the unlock for almost everything above.
2. **The Joined Inventory page** (the killer).
3. **The first three or four compliance checks as Searches** (shadow buckets, sigstore-green, N4/N5-past-SLA, OAC-present) with a "Run checks" panel that produces findings.
4. **Component Detail page** with the history panel.
5. **VDR Posture heatmap** if time.

Skip the artifact library and the KPI dashboard for the demo. Sam already
has those.

## What this wishlist deliberately defers

- Information-flow as edges (currently a JSON field on `ksi_component`; flow-edge decomposition is a named v0 non-goal).
- A global vulnerability / CVE registry node (vuln-management theme proper; current per-finding evaluation lives on `vdr_finding` already).
- OSCAL / IIW decomposition (permanently not planned — they're renderings of the KSI inventory, decomposing them re-models it).
- The `compliance_check` model (v0 = `Search` + interpretation; revisit when there's a second consumer).
