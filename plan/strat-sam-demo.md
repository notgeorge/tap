# Sam Demo

Let's lay out the exact moves to accomplish between here and the Sam demo tentatively scheduled for June 1st.  This will cover both the demo progression as well as feature development needs.  The process of writing this doc will help dial in our strategy-management process which has to account for timelines, feature development, marketing, partnerships and more while tying back into the overall roadmap.

The demo is based on a clone / re-launch of sam's website which has been lightly tailored to run inside our AWS account.  We'll be pulling from that for the demo, leaving his production site un-touched.  All evidence will be real, live, and 

## Goals

1. Deliver a mind-blowing demo to Sam that begins to position him as a advocate / customer / advisor (a model for future demos to founders)
2. Build out necessary features to "make it work" against a live, super small scale system
3. Refine the rodmap / strategy / tactic process


## Demo Flow

Work in progress based on the learning more and more about the site:

Opening Patter
- so i've been on sabbatical, which is mostly true...
- fedramp vs assessments vs coding
- set fedramp 20x as a target
- been needing an initial target to play around with...

Loads up Page
- let sam figure it out.
- i took some liberties to do what i think you'd want to see
- happy to show you around, what would you like to see
- let him drive

Sites to See
- 
- scheduler system (his + fedramp ksi's)
- dig into individual nodes / edges

### Demo Psychology
Pulling back and thinking of this as a repeatable demo to founders

- **Overview Effect**:  They've never seen their system before, not in its entirety  - the grid grounds.
- **Cognitive Relief**:  Having a place to see it is a cognitive relief which they've been carrying forever - the grid remembers
- **Visual Proof**:  Sense of pride, ownership, accomplishment, validation, they know it works, now everyone can **see** it.
- **New Ownership**:  Like coming into a new house, openning doors, finding features and affordances
- **Total Control**:  Let them find where they want to see new things (be prepared to build them fast) - sophisticated beanbag

My role in the demo:

A key point:  I'm the conceirge to the experience they're having.

- Architect - Explain what their seeing, how the system works under the hood
- Collaborator - While building it out i noticed / have a question about...
- Owner Myself - I've built my own system after many long years I can see it too

### Demo Beats

This whole thing plays out like the end of a house-remodel show or the prize reveal in the price is right when working with product people.  

- Patter:  Opening framing, audience sees me, set the tone
- Reveal:  First page load, this is something new
- Orient:  Holy shit moment this is their site, guide to a few places of interest as they adjust
- Explore:  Let them drive 
- Explain:  Describe what's going on behind the scenes
- Future:  Discuss where this could go, end on concrete next step(s)

Note:  There will be some magic going on in here and other presentation formats

### Key Points from Demo
1. Enhance - sam's done good stuff, we're adding to it
2. Explore - show, don't tell. just have the surfaces for him to explore.
3. Extend - this is a robust platform (scheduler, collector, nodes, edges, pages, graph views)


## Suggestions Back to Sam

Findings worth mentioning to Sam — things we noticed while reproducing his
site that would improve the upstream application. Add to this list as we
encounter more during demo prep.

Working from `github.com/sam-aydlette/samaydlette.com` upstream/main as of
2026-05-20 (fetched into the local fork at `~/Documents/code/samsite/`,
remote `upstream`).

### Terraform tag coverage

**What we found.** Upstream `infrastructure/main.tf` tags exactly four
resources: `aws_cloudwatch_log_group.route53_query_log`,
`aws_iam_role.lambda_opa`, `aws_lambda_function.opa_compliance`, and
`aws_cloudwatch_event_rule.opa_compliance`. His S3 bucket, CloudFront
distribution, Route53 zone, and ACM cert are all `data` references in the
upstream — Sam created them manually beforehand, so whatever tags they
carry in his account came from the AWS console rather than his Terraform.
There's no `local.common_tags` map, no provider `default_tags` block, and
no `Project` / `System` tag identifying these resources as belonging to
"samaydlette.com" as a whole.

**Why it matters when something like Rampart looks at the account.** Without
a consistent project-level tag, an inventory tool can't programmatically
distinguish "the site" from anything else in the AWS account. Sam's tagging
discipline today gets you 4 of his ~7 user-facing resources; the
remaining 3 (S3 bucket, CloudFront, the auto-created Lambda log group) are
identifiable only by name pattern.

**Concrete suggestions:**

1. **Add a provider `default_tags` block** so every resource the provider
   creates inherits `Project=samaydlette.com` (or whatever the system name
   should be), `Owner`, `Environment`, `CostCenter`. AWS provider supports
   this natively since v3.38.
2. **Add a per-resource `Component` (or `Subsystem`) tag** for the natural
   tier shape — `site` (S3 + CloudFront), `compliance` (Lambda + role +
   EventBridge + log group), `dns` (zone + cert if/when he stops referencing
   them as `data`). Three values, big payoff for any future projection /
   compliance / cost-allocation tool.
3. **Declare the Lambda log group explicitly** as an
   `aws_cloudwatch_log_group` resource with the canonical
   `/aws/lambda/<function-name>` name + a `retention_in_days` + tags. AWS
   silently creates it on first Lambda invocation otherwise, and that
   silently-created log group is permanently outside Terraform's view —
   never tagged, never reapable.
4. **Decide whether the manually-created S3 bucket / CloudFront / Route53
   zone / ACM cert should become Terraform-managed resources** (with the
   `lifecycle.prevent_destroy = true` guard for safety) or stay as `data`
   references. Either choice is defensible; what's brittle is the current
   middle ground where his TF assumes they exist and silently breaks if
   they don't, with no tagging discipline applied.

**Not Sam's fault (ours):** The Route53 zone + ACM cert in our cross-account
deployment are also untagged, but those live in `domain.tf` which we
added — that file does not exist upstream. Worth disclosing if/when this
suggestion comes up in conversation so Sam knows we're being honest about
which gaps were his vs. ours.

## Things to build
[x] Samsite: Cross-deployment of his site in my account (done)

Samsite Plugin
- collector: grabs artifacts from sam's site, verifies authenticity of docs, creates nodes
- models:  new models for his system like rekor, inventory json, and so forth
- graph view:  custom view of his overall system, boundary, ideally including paths
- view pages:  visualize key artifacts including x, y, z

TAP Core
[-] AWS Collector:  in-flight now focused on gathering exactly the instance types sam's site uses (start first)
- Paths:  define the v0 paths system and apply it to the paths he has in his arch diagram (start after graph view)
- Navigation:  standardize how nav takes place across all pages and plugins

### Bonus
- History UI:   pretty history and FLIP fields that we can show off
- Batch UI:  Need to actually build this out, drive home batch provenance

### Ideas for the Future
- DCOM: perform a comparisson between his configured grid and the operational grid to assess drift (first pass at DCOM, but we can always just speak to it)
- Terraform Collector:  Parse his github repository to use the terraform to gather a view of his site - https://github.com/sam-aydlette/samaydlette.com on a configuration dimension including his compliance checking machinery (who watches the watcher). 
- Dimensionality:  Use the config and ops graphs to formalize how this is collected and presented in the system.  First real-world test of dimensions, demand-driven as it should be

## Build Process

### 1. Samsite  
Status: Done  

Need this first, it's the foundation for gathering the samsite info.  

### 2. AWS Collector  
Status:  Done  

This gathers the aws events and chucks them into the grid.  they're the foundation for everything we're building next.

### 3. Sam Plugin
Status:  Next Up  

Coming next, lays the foundation for the visualization, pages, and collectors that we'll build to make this work.

Once the core plugin, models, collector, and pages are created we'll turn attention to refinements and flair

#### Sub-Tasks
1. Plugin: Initail plugin infrastructure created using the create plugin skill, load it up on a sam-specific worktree
2. Graph View:  Get started on building out the first page that has the canonical view, this will take some tweaking, start early
3. Collector:  Go out to our site and pull down critical files, this will drive model creation and inform pages we want to build
4. Models:  create necessary models, identify bonus-points modules, add a boundary to the KSI plugin :)
5. Pages:  decide which pages to create, place them in this list as sub-bullets

Anything else.

---

## Decision Log

Captured as we go — the "strategy management" surface for this demo.

### 2026-05-20 — First-pass landing page

**Decision: scout the cruft before curating.**
George's collection account (180731181784) has been his beater account
since before EC2 had persistent storage. First boto3 sweep across us-east-1
+ us-east-2 returned 58 nodes / 5 edges — including ~36 IAM roles and 12 S3
buckets that are almost certainly legacy debris. Rather than guess, the
samsite landing page pass-1 dumps **everything** the collector returned,
no filtering, no layout sophistication, so we can see exactly what's there
and decide which buckets/roles/log-groups are demo-meaningful vs. cruft to
mute. The curated projection is a pass-2.

**Decision: mint the `aws_account` node in samsite GRIFT for v0 (not in the collector).**
The boto3 collector emits dimensions `{cloud:"aws", aws_account:"...",
aws_region:"..."}` on every node but does NOT emit an `aws_account` node or
`BELONGS_TO_ACCOUNT` edges — account is currently a dimension, not a node.
The demand signal from this work is that the collector should own account
emission (singleton derived from STS GetCallerIdentity + per-node
BELONGS_TO_ACCOUNT). Until then, samsite mints the account node and the
projection JS synthesizes containment via the `aws_account` dimension on
each node. **Backlog:** add `aws_account` to the aws_core manifest as a
custom-fn-sourced singleton; emit BELONGS_TO_ACCOUNT for every resource.

**Decision: no new models or edges for v0.**
We reuse aws_core's models and edges. The new-plugin skill steps for
models/edges are intentionally skipped on pass-1; samsite ships as a
projection/page plugin only. When samsite-specific concepts arrive
(rekor signatures, sigstore bundles, KSI catalog overlay, boundary), they
get their own add-model/add-edge passes.

**Decision: override the landing page.**
genericom currently owns the default `landing_page` (administrivia ceded
it via batch v0.2.0). samsite replaces it via a higher-version
`landing_page → USES_LANDING_PAGE → /samsite` batch. Genericom's
landing-page batch is left intact for now — it stops being the default
once samsite's GRIFT loads.

### 2026-05-20 — System-identification: tag the source, not the grid

**Decision: use AWS tags as the system-identification primitive, not dimensions.**

When pass-1 surfaced the cruft we needed a way to separate Sam's actual
resources from George's legacy beater-account debris. The strategic options
considered:

1. **Dimensions on entities, applied via post-collection hook.** Architecturally
   clean (dimensions are the right shape long-term, and TAP already stamps
   `{cloud, aws_account, aws_region}` dimensions on every collected node), but
   requires either touching Gryphon for dimension-aware predicates OR a samsite
   one-off post-collection hook that bulk-patches dimensions. Both feel like
   building plumbing the demo doesn't need yet.

2. **AWS tags.** The boto3 collector already pulls tags (RGTA sweep + per-service
   side-quests for IAM roles), and the ORM search compiler can filter on the
   per-model `tags` JSON column with a small extension. AWS-native, well-trod
   pattern, no new TAP primitives required.

3. **Graph reachability from a known anchor.** Most "TAP-native" but unnecessary
   when tags already give us a clean signal.

Chose **(2) — AWS tags.** Reasons: it's the well-trod cloud-native path
that we'd want to exercise anyway; the tag data is already in the grid;
samsite's Terraform creates every demo resource, so we control the tag
discipline at the source; and it sidesteps premature Gryphon work.

**The tag shape we'll standardize on (Sam's TF + our cross-account stacks):**

```
Project   = "samsite"                                     (universal namespace marker)
Component = "site" | "compliance" | "dns" | "bootstrap"   (4-tier system shape)
Owner     = "sam-aydlette" | "platform"                   (existing: who owns intent)
ManagedBy = "terraform-bootstrap" (where applicable)      (existing: deploy tier signal)
Environment / CostCenter / DataClassification / Name      (existing pass-through)
```

The 4-tier `Component` split is the real architectural payload — it
distinguishes "the site," "the watcher," "the names," and "the deployer."
Worth preserving as a first-class projection skeleton: account →
(site, compliance, dns, bootstrap) → resources.

**Tag tier → resource mapping (confirmed in collected data 2026-05-20):**

| Component  | Resources |
| ---------- | --------- |
| site       | S3 `samsite-prod-1`, CloudFront `ddqsj3lyxiv8s.cloudfront.net` |
| compliance | Lambda `samsite-prod-1-opa-compliance`, IAM role `samsite-prod-1-lambda-opa-role`, EventBridge rule `samsite-prod-1-opa-compliance`, log group `/aws/lambda/samsite-prod-1-opa-compliance` |
| dns        | Route53 zone `samsite.unified-systems.com.`, ACM cert `samsite.unified-systems.com` |
| bootstrap  | S3 `your-org-samsite-tfstate-1`, DynamoDB lock table, GitHub OIDC provider, IAM role `samsite-deploy` |

**Build path:**
1. TF diff against `~/Documents/code/samsite/` — provider `default_tags` blocks
   in `main.tf` and `bootstrap/main.tf` (Project + Owner + Environment +
   CostCenter), per-resource `Component` tag, tag blocks added to `domain.tf`'s
   Route53 zone + ACM cert, explicit `aws_cloudwatch_log_group` for the Lambda
   (currently auto-created and untagged).
2. `terraform apply` in `bootstrap/` and `infrastructure/`.
3. Re-run the boto3 collector. Every demo resource now carries
   `Project=samsite` + `Component=<tier>`.
4. Samsite landing search filters on `tags.Project = "samsite"`; pass-2 layout
   nests by `Component`.

**Backlog (aws_core boto3 collector) — tag-derived dimensions.**

When real multi-tenant or second-customer pressure forces it, build a
configurable mapping from collected tags → entity dimensions (e.g.
`tag.Project` → `dimension.tap.project`). Required controls because
**dimensions will also be the security-boundary pillar** and arbitrary
user-controlled tags must not silently become security boundaries:

- per-collector or per-account allowlist of which tags may become dimensions
- denylist for reserved TAP dimension prefixes (`tap.*`, `aws.*`, etc.)
- collision/conflict handling when multiple sources map the same tag key
- FLIP provenance: which collector run wrote which dimension on which node
- explicit policy on what happens when a previously-mapped tag value changes
  (re-stamp, history, or both)

Deferred: samsite uses the well-trod tag path directly for the demo. The
demand signal for actually building this lands when there's >1 system being
collected into one account, or >1 customer being collected at all. Mirror
to `plugins/aws_core/specs/spec-aws-core-collector-v0.md` backlog.

### 2026-05-20 — `GeorgeAddition` tag: mark our cross-deployment additions

**Decision: tag every resource we added (and not in Sam's upstream) with a
single `GeorgeAddition` key whose value is a free-text "why."**

The "Suggestions back to Sam" comparison surfaced a useful demo affordance:
if we tag exactly what we added on top of Sam's original architecture,
both the demo UI and the conversation with Sam can quickly distinguish
"this is Sam's system" from "this is the cross-deployment scaffolding
George needed to make it run in his own AWS account." Absence-of-tag is
the signal for "this is Sam's." Value is the one-line story, scoped to
≤256 chars (AWS tag-value limit).

**Resources tagged** (9 — every taggable resource we added):

| File | Resource | Value |
| --- | --- | --- |
| `main.tf` | `aws_s3_bucket.website` | `data→resource conversion for cross-account deploy; upstream uses data.aws_s3_bucket` |
| `main.tf` | `aws_cloudfront_distribution.website` | `data→resource conversion for cross-account deploy; upstream uses data.aws_cloudfront_distribution` |
| `main.tf` | `aws_cloudwatch_log_group.opa_compliance` | `explicit log-group declaration so it's tagged + has retention; AWS otherwise auto-creates it untagged` |
| `domain.tf` | `aws_route53_zone.samsite` | `cross-account custom domain: subdomain Route53 zone delegated from GoDaddy-hosted apex` |
| `domain.tf` | `aws_acm_certificate.samsite` | `cross-account custom domain: TLS cert for the subdomain (must be us-east-1 for CloudFront)` |
| `bootstrap/main.tf` | `aws_s3_bucket.tfstate` | `bootstrap stack: remote Terraform state backend for the main stack` |
| `bootstrap/main.tf` | `aws_dynamodb_table.tflock` | `bootstrap stack: Terraform state-lock table` |
| `bootstrap/main.tf` | `aws_iam_openid_connect_provider.github` | `bootstrap stack: GitHub Actions OIDC federation; replaces upstream's long-lived IAM-keys pattern` |
| `bootstrap/main.tf` | `aws_iam_role.deploy` | `bootstrap stack: GitHub Actions deploy role assumed via OIDC; scoped to main-stack resources` |

**Not tagged** (would have been but AWS doesn't accept tags on the
resource type): `aws_cloudfront_origin_access_control.website`,
`aws_acm_certificate_validation.samsite`, the `aws_route53_record.*`
validation + alias records, the S3 sub-resources (`aws_s3_bucket_versioning`,
`_server_side_encryption_configuration`, `_public_access_block`,
`_policy`), `aws_iam_role_policy.deploy`. They're carried by their parent
resource in the demo regardless.

**Demo affordance.** In the curated samsite projection, every node with
`tags.GeorgeAddition` present gets a visual marker (badge/border/etc. —
shape TBD when we build it) and the tag value appears in the info panel.
Tells the story honestly without us having to narrate it.

**Apply-time charset cleanup.** The values above were written with
prose punctuation (em-dashes, semicolons, arrows, parens, apostrophes).
AWS tag values restrict to letters/digits/spaces plus `+ - = . _ : / @`,
so the parallel deploy session had to flush those out before apply
(`→` ⇒ `-to-`, `;` ⇒ `-`, parens ⇒ `-`, etc.). Meaning preserved. Rule
saved in agent memory (`feedback_aws_tag_value_charset`) so future IaC
tag-value drafting stays inside the AWS-legal charset from the start.

### 2026-05-20 — Tag landing verification (post-apply re-collection)

Collector re-ran after `terraform apply`. **9 resources now carry
`Project=samsite`** — exactly the demo set, perfectly grouped by `Component`:

| Component  | Resources |
| ---------- | --------- |
| site       | S3 `samsite-prod-1`, CloudFront `ddqsj3lyxiv8s.cloudfront.net` |
| compliance | Lambda, EventBridge rule, IAM role `samsite-prod-1-lambda-opa-role`, log group `/aws/lambda/samsite-prod-1-opa-compliance` |
| dns        | ACM cert `samsite.unified-systems.com` |
| bootstrap  | S3 `your-org-samsite-tfstate-1`, IAM role `samsite-deploy` |

**6 of those 9 carry `GeorgeAddition`** — exactly the resources we
authored or converted (the data→resource pair + the explicit log group +
ACM cert + the two bootstrap-stack pieces in the collector's view).

**Two visible collection gaps surfaced** (not blockers, worth filing):

1. **Route53 zone tags are not collected.** The zone exists, was tagged by
   the apply, and `aws_route53_zone.samsite` carries `Project=samsite` +
   `Component=dns` + `GeorgeAddition` in AWS — but the boto3 manifest has
   no `tags` block for the `aws_route53_zone` entry, so `tags = {}` in the
   grid. Fix: add a `tags = { source: "service", op: "ListTagsForResource",
   ... }` block to the `aws_route53_zone` manifest entry. Small honest
   addition; ACM has the same gap shape but our cert is on a different
   tag-collection path that already works.
2. **DynamoDB tflock + GitHub OIDC provider aren't collected at all.**
   `aws_dynamodb_table` and `aws_iam_openid_connect_provider` aren't in
   the boto3 manifest. The DynamoDB model exists in `aws_core/models/`
   but isn't registered for collection. The OIDC provider has no model
   yet. Both are out-of-scope for the samsite demo set today (so this
   landing-page filter stays correct), but the bootstrap-tier picture is
   incomplete until those two get added. Worth noting in the demo "what
   we collect" walkthrough as a known boundary.

Both gaps belong on `plugins/aws_core/specs/spec-aws-core-collector-v0.md`
and `spec-aws-core-v0.md`; deferred for now since the demo set is intact.

### 2026-05-20 — Autonomous pass: closed both collector gaps + added OIDC model

George was on a walk; agent ran with a declared scope-fence and 3 phases.

**Phase 1 — Route53 zone tag collection.** Manifest schema's `service`-source
tag block was single-param-only (`param` + `param_from`); Route53's
`ListTagsForResource` needs two params (`ResourceType` literal +
`ResourceId` from path). Widened the schema to a `params` dict where each
entry is `{literal:"..."}` or `{from:"path"}`. Migrated the existing
IAM-role and CloudFront entries to the new shape. Added tag block to the
`aws_route53_zone` entry. `route53_zones_with_alias_targets` custom_fn
now also yields `_zone_resource_id` (bare zone-id segment) so the tag
block's `ResourceId` resolves without a transform.

**Phase 2 — DynamoDB tflock collection.** Added `tags` JSONField to the
existing `DynamoDbTable` model (+ migration). New `dynamodb_tables_described`
custom_fn does the ListTables→DescribeTable fan-out and yields the inner
`Table` dict so `TableArn` is at the root for `natural_key`. New
`aws_dynamodb_table` manifest entry with RGTA-sourced tags (`dynamodb:table`).
RGTA already covered it; one new node lands: `samsite-tfstate-lock`.

**Phase 3 — GitHub OIDC provider model + manifest + FEDERATES_INTO edge.**

- New model `IamOidcProvider` (`aws_iam_oidc_provider`) with fields:
  `name`, `provider_arn`, `url`, `client_ids`, `thumbprints`, `tags`,
  `configuration`. Migration applied.
- New `iam_oidc_providers_described` custom_fn does ListOpenIDConnectProviders
  → GetOpenIDConnectProvider fan-out, embeds the source ARN as `ProviderArn`
  on each yielded dict (GetOpenIDConnectProvider doesn't echo the ARN back).
- Manifest entry uses `service`-sourced tags via `ListOpenIDConnectProviderTags`
  + the new multi-param dict shape.
- New edge type `FEDERATES_INTO` (sources: `aws_iam_oidc_provider`,
  targets: `aws_iam_role`). The IAM role manifest entry got an edge rule:
  `value_path: AssumeRolePolicyDocument.Statement[].Principal.Federated`,
  `direction: inbound` (provider → role).

**Adjacent engine fix.** While wiring Phase 2 I found a quiet bug: the
collector engine passed only `session` as `fn_context` to custom_fns, with
no region binding. Worked for `s3_buckets_hydrated` (S3 ListBuckets is
location-flexible) and `route53_zones_with_alias_targets` (Route53 is
global; the custom_fn hardcodes us-east-1), but `dynamodb_tables_described`
(regional) couldn't build a region-bound client. Fixed by passing
`client_for` through to custom_fns as a kwarg, and updating all four
custom_fns to accept `client_for` (the regional one uses it, the global
ones accept-and-ignore). One-line change in `source.py`, kwarg added to
each custom_fn signature.

**Final state (post-phase-3 recollection):**

- **61 aws_* nodes** (up from 58): +1 DynamoDB, +2 OIDC providers.
- **7 edges** (up from 5): +2 FEDERATES_INTO edges.
- **12 nodes carry `Project=samsite`** (up from 9), grouped:

| Component  | Count | Resources |
| ---------- | ----: | --------- |
| site       | 2 | S3 `samsite-prod-1`, CloudFront |
| compliance | 4 | Lambda, IAM role, EventBridge rule, log group |
| dns        | 2 | Route53 zone *(NEW Phase 1)*, ACM cert |
| bootstrap  | 4 | tfstate bucket, deploy role, DynamoDB tflock *(NEW Phase 2)*, GitHub OIDC *(NEW Phase 3)* |

- **9 of those 12 carry `GeorgeAddition`** — the cross-deployment additions.
- **Bonus FEDERATES_INTO edge surfaced for free**: pre-existing Teleport
  OIDC federation (`criticalsec-connect.teleport.sh -> TeleportConnectDemo`)
  also matches the role-trust-policy pattern, so it landed too. Not part
  of samsite — but a real federation relationship now visible on the grid.

**Spec catch-up still owed.** The schema/engine changes in this pass
deserve to be reflected in `plugins/aws_core/specs/spec-aws-core-collector-v0.md`
under the manifest section: (a) the `service` tag block's new multi-param
shape, (b) the `client_for` kwarg on custom_fn signatures. Not done in
the autonomous run — flagging here so a future pass can reconcile.

### Pass-1 Backlog (de-prioritized; revisit after we see the cruft)

- Daily scheduler node that re-runs the boto3 collector against this account.
- aws_account / BELONGS_TO_ACCOUNT in the aws_core manifest itself.
- aws_region nodes pruned to the account's actual scope (collector currently
  doesn't link account → region).
- IAM role / S3 bucket "demo allowlist" — mark which resources are real-Sam
  vs. legacy cruft; mute the cruft in the curated projection.
- Lambda-internals page (peer of genericom's EC2-instance page): drill into
  the OPA-compliance Lambda, show role + log group + EventBridge schedule.
- Rekor / sigstore models for the OPA gate's signing chain.
- KSI catalog ingestion (his `infrastructure/schemas/ksi-catalog.json`) +
  scoreboard projection against this account.

### Session housekeeping

- 2026-05-20 — Fixed broken landing placeholder: `tap_web/views.py:_render_grid_placeholder`
  was importing the (since-removed) `_enrich_nodes_with_icons` from
  `tap_web.panels.table_panel`. Hit when no `landing_page` is configured.
  Repaired by switching the placeholder's `execute_search` calls to
  `layer="extended"` and dropping the manual icon + edge-name enrichment —
  commit 96cf36e ("GRIFT subgraph spec") moved both into the extended-layer
  serializer; the placeholder was the lone unmigrated caller.

### Pass-1 observations (2026-05-20)

What the first sweep (us-east-1 + us-east-2, 58 nodes / 5 edges, SUCCESSFUL)
actually surfaced once the landing page rendered it:

| count | type | notes |
| ---: | --- | --- |
| 1 | aws_account | the synthetic container we minted in samsite GRIFT |
| 1 | aws_lambda | `samsite-prod-1-opa-compliance` — the demo-meaningful Lambda |
| 1 | aws_cloudfront_distribution | `ddqsj3lyxiv8s.cloudfront.net` — Sam's CDN |
| 1 | aws_route53_zone | `samsite.unified-systems.com.` — Sam's DNS |
| 1 | aws_eventbridge_rule | the daily compliance-check schedule |
| 3 | aws_acm_certificate | 1 demo + ~2 legacy |
| 3 | aws_cloudwatch_log_group | 1 demo + ~2 legacy |
| 12 | aws_s3_bucket | **mostly cruft** (the demo bucket is `samsite-prod-1`) |
| 36 | aws_iam_role | **mostly cruft** (this is an old account) |
| 34 | aws_region | **base-seed reference data** — not account-scoped |
| 108 | aws_az | **base-seed reference data** — not account-scoped |

Real edges connecting things: ROUTES_TRAFFIC (zone→CDN), RETRIEVES_CERT_FROM
(CDN→cert), RETRIEVES_CONTENT_FROM (CDN→bucket), WRITES_LOGS (lambda→log
group), ASSUMES_ROLE (lambda→role). The Sam-demo spine is *all there in
the first sweep* — 5 nodes + 5 edges. The other ~190 entities are cruft
plus reference seed data.

**Pass-2 priorities, in order:**

1. Drop the global `aws_region` + `aws_az` reference-data from the
   landing-page search (they're not in dimension `aws_account=180731181784`
   — they're shipped by aws_core as global seed). Trivial: add a dimension
   filter to samsite's search.
2. Mark the demo-meaningful resources vs. legacy cruft. Three viable paths:
   (a) explicit "demo allowlist" GRIFT in samsite, (b) a `cruft:true`
   dimension applied via service-layer tag command, (c) name-prefix filter
   for `samsite-prod-1`. (a) is most honest, (c) is fastest for demo day.
3. Containment under `aws_account` — implement once we know what's in scope.
   Either ship BELONGS_TO_ACCOUNT edges through the collector manifest (the
   right durable answer) or synth them in a samsite projection JS.
4. Once curated, the projection nests `aws_route53_zone → aws_cloudfront →
   aws_s3_bucket` as the visible spine, with the Lambda + role + log group +
   EventBridge rule forming the "compliance machinery" cluster — both
   inside the account.

Screenshot of the unfiltered pass-1 view lives at
`samsite-landing-pass1.png` (in the worktree root, not committed).




