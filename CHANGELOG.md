# Changelog

## [0.1.4](https://github.com/unified-systems-com/tap/compare/v0.1.3...v0.1.4) (2026-08-21)


### Features

* **cicd:** plugin release SBOM lane — reusable workflow + generator (req-cicd-sbom-10) ([970c151](https://github.com/unified-systems-com/tap/commit/970c151ed9793f487dec41d0099881b8ff52be7a))
* **cicd:** reviewer-seat credential patterns + manage-secret record for OPENAI_API_KEY / XAI_API_KEY ([4b0a7f1](https://github.com/unified-systems-com/tap/commit/4b0a7f1c12011b686b9cba6f58bbe381b30d5333))
* **cicd:** SBOM generation lane — implement req-cicd-sbom-1..7 + -11 ([dadbee9](https://github.com/unified-systems-com/tap/commit/dadbee97634612c12d88845aef9d94f5347a13f6))
* **cicd:** two-account code-owner review — [@criticalsec](https://github.com/criticalsec) co-owns all plumbing paths ([318927b](https://github.com/unified-systems-com/tap/commit/318927bda770b70ccd07414c9588cc625a250c76))
* **cicd:** Unified AI Review shims — two-stage harness live on tap (advisory) ([47f7561](https://github.com/unified-systems-com/tap/commit/47f7561f788cea29537c24301d8ca3c5cea3a3a7))
* **cicd:** verified wheel-cache seed — implement req-cicd-supply-chain-provenance-2 ([391b590](https://github.com/unified-systems-com/tap/commit/391b5908958215504cb4f2e6ccb429811f0855f9))
* **dev:** pr-review-triage — read the AI review before the merge lands ([4660285](https://github.com/unified-systems-com/tap/commit/46602858708fadbefbaa4408c7a61bc859fdf634))
* **dev:** pr-review-triage — read the AI review before the merge lands ([076f2e7](https://github.com/unified-systems-com/tap/commit/076f2e720acbce5440d1ea8f6afbdd235285cac0))
* **specs:** claims fingerprint the code end — the Doorstop model ([d882578](https://github.com/unified-systems-com/tap/commit/d8825785531bec62ba931c7f500157ac61c4d54f))
* **specs:** dupes-campaign surfaces join the traceability accounting ([1405827](https://github.com/unified-systems-com/tap/commit/140582718d354393a569041b076ae71d56ecbab0))
* **specs:** five ledger rulings land — the review ledger empties ([5068ce8](https://github.com/unified-systems-com/tap/commit/5068ce89141a6ed5137e1756e289a5199fa8d89f))
* **specs:** Wave A — the Definition of Done and its accounting model ([64be039](https://github.com/unified-systems-com/tap/commit/64be0393ab5a659fddee91b84b3ee3d2624de688))
* **specs:** Wave B — dispositions, accounting, and the Unaccounted ratchet ([899a1c6](https://github.com/unified-systems-com/tap/commit/899a1c6983216567c325a0448c4d7723087517e4))
* **specs:** Wave C batch 1 — Unaccounted 1,072 -&gt; 509, and the triage skill ([4e9b024](https://github.com/unified-systems-com/tap/commit/4e9b024a15f87a8bb5d601caf58e5f06cc2baccb))
* **specs:** Wave C batch 2 — the guard-rid harvest, Unaccounted 509 -&gt; 495 ([c200772](https://github.com/unified-systems-com/tap/commit/c200772469be411d27762a7e08e9dafc24f47e1a))
* **specs:** Wave C batch 4 — the gryphon claim batch, Unaccounted 467 -&gt; 447 ([0784bcc](https://github.com/unified-systems-com/tap/commit/0784bcc708c8b47185a3daac7dd6bdf2f374ec77))
* **specs:** Wave C batch 5 — boot + cares-secrets sweeps, Unaccounted 446 -&gt; 434 ([f4b894e](https://github.com/unified-systems-com/tap/commit/f4b894ece291296eab0704ea435e6110d6ba77b3))


### Bug Fixes

* **cicd:** attest sbom-path takes concrete paths, not globs ([e75ee7d](https://github.com/unified-systems-com/tap/commit/e75ee7dfdd68fc11b27fca9867e23b845bc0f9fb))
* **cicd:** bounded retry on every apk add — Wolfi repo flakes twice in five days ([5b04dc9](https://github.com/unified-systems-com/tap/commit/5b04dc91ba4a4b523ec514a6eb46d3bca4f5b7d6))
* **cicd:** bounded retry on every apk add — Wolfi repo flakes twice in five days ([c3f233d](https://github.com/unified-systems-com/tap/commit/c3f233d4240effca37c80facebfae57afd97b2e2))
* **cicd:** Copilot triage on [#86](https://github.com/unified-systems-com/tap/issues/86) — shape-robust parsing + spec status sync ([ba9f052](https://github.com/unified-systems-com/tap/commit/ba9f0520d53b77ad44869075a9b11d9266d98b85))
* **cicd:** legacy images degrade instead of brick + red seed-verify dumps the whole story ([8ad17d6](https://github.com/unified-systems-com/tap/commit/8ad17d65204ae1f026ad8d8a7aad4a9d82c58511))
* **cicd:** OpenAI seat rides the 60k-TPM long-context pool ([ff4da36](https://github.com/unified-systems-com/tap/commit/ff4da361adb1eb5b46ba9fe8bd9d90addcae7828))
* **cicd:** pin schemathesis's validation engine — jsonschema-rs 0.50.0 broke the deterministic gate ([5a6f8e2](https://github.com/unified-systems-com/tap/commit/5a6f8e26cbc926d4025cfd65bfb5027e7df5f9d3))
* **cicd:** post-merge triage batch — zip-slip belt, no asserts in gate code, exactly-one wheel ([71ada21](https://github.com/unified-systems-com/tap/commit/71ada21fd889b2674da41410a051d1ec02bc0e6a))
* **cicd:** release detection matches merge-commit bodies — contains, not startsWith ([b3bc3e8](https://github.com/unified-systems-com/tap/commit/b3bc3e8f947c0b82819cabea21822acc7e63cc61))
* **cicd:** retry loop logs the failed attempt before the final exit ([fcb386f](https://github.com/unified-systems-com/tap/commit/fcb386f376ede1f2eacc2cfc19aedf51c4d1c63e))
* **cicd:** rids job resolves its Python from pyproject requires-python ([c497339](https://github.com/unified-systems-com/tap/commit/c497339ee5dc495f7e9004dec2835aca66b7705f))
* **cicd:** schemathesis 4.25.0 + jsonschema-rs pinned forward to 0.50.0 ([51684c3](https://github.com/unified-systems-com/tap/commit/51684c3d914d0ad86bb6e3e686393579343b6bef))
* **cicd:** seed-verify report — typed locals instead of type-ignore juggling ([f8cd65c](https://github.com/unified-systems-com/tap/commit/f8cd65c9d1627c7f267ed82a54a82b0f843d3a39))
* **cicd:** the rids job gets Python 3.14 — the codebase is py314-native by force ([942f74d](https://github.com/unified-systems-com/tap/commit/942f74dd4947430fb2b7cbf70230d69e7039c9b3))
* **dev:** pr-review-triage — Copilot triage of the triage tool ([ed37071](https://github.com/unified-systems-com/tap/commit/ed37071ea26404f40cbb11ee2b3028b40c18661e))
* **dev:** pr-review-triage — the Copilot fixes that missed PR [#83](https://github.com/unified-systems-com/tap/issues/83)'s merge ([04c7740](https://github.com/unified-systems-com/tap/commit/04c7740e84cfbb9d2d98d77fe8ca224e3f0691ee))
* **dupes:** F2 — the boot-profile enabled default agrees fail-closed everywhere ([f87d73d](https://github.com/unified-systems-com/tap/commit/f87d73d73405cd131bb31ccb75f7f6214735ae8f))
* **dupes:** F5 — one declared-digest parse, duplicate record names fail hard ([589110d](https://github.com/unified-systems-com/tap/commit/589110d8ae376ea5993276a10c0b1461f53d9f35))
* parenthesize every bare multi-exception clause — host-python compatibility ([3918182](https://github.com/unified-systems-com/tap/commit/3918182c5917c50ea5c8f58dce6be91adcfed64d))
* parenthesize every bare multi-exception clause — host-python compatibility ([fe2003c](https://github.com/unified-systems-com/tap/commit/fe2003cb6e25339fdae792fdd3b895b0e1f2fdfb))
* **specs:** generated blocks leave the requirement hash — the Map-sync churn closes ([61ca046](https://github.com/unified-systems-com/tap/commit/61ca046d30140bb5a6a61c751efb8323987b904a))
* **specs:** merge reconciliation — Map claim resync + SBOM citations onto the renamed plugin namespace ([a39199e](https://github.com/unified-systems-com/tap/commit/a39199e10b85ca61e14766c861f383935b25bb04))
* **specs:** parenthesize multi-exception clauses — the server rids job runs bare python3 ([39d298f](https://github.com/unified-systems-com/tap/commit/39d298f1dd9fcd60c86d9996546683cb6ac0a538))
* **specs:** Wave C batch 3 — status normalization, Unaccounted 495 -&gt; 467 ([747c7ea](https://github.com/unified-systems-com/tap/commit/747c7ea271e1441d210754965299e4f98358f4e0))


### Documentation

* **cicd:** concrete per-arch SBOM verification path (sbom-5, P2) ([6e53592](https://github.com/unified-systems-com/tap/commit/6e53592b02f254be932cf623a1a674fab06bd36e))
* **cicd:** confidence calibration recorded as a future seam ([964746c](https://github.com/unified-systems-com/tap/commit/964746c7b8d6ab792c3073679165ae4f55da0913))
* **cicd:** conformance validation, out-of-band detection gate, ecosystem coverage (req-cicd-sbom-11..13) ([49bb426](https://github.com/unified-systems-com/tap/commit/49bb4262f73138463b8bf67a72675a3e59b966f5))
* **cicd:** doctrine 4 (the maintainer is not special) + bypass-emptying recorded + org-wide end state ([d82d32e](https://github.com/unified-systems-com/tap/commit/d82d32e7b631ca3257399aa2e19dc3d9a01e19ee))
* **cicd:** emit CycloneDX + SPDX both, day one, from the single derivation (sbom-6, P2) ([0178426](https://github.com/unified-systems-com/tap/commit/017842621fdb1862d8f0d910764bdfe8a7e20a3c))
* **cicd:** five Codex nits — current attest action, exact SPDX predicate URI, dual-schema validation, path + wording fixes ([773f769](https://github.com/unified-systems-com/tap/commit/773f7698020643ac0c66d2c01df74f2ca8714816))
* **cicd:** fold in George's in-flight review — two-repo split, radar deferrals, loud failures, deterministic screens, plumbing CODEOWNERS ([5ba4895](https://github.com/unified-systems-com/tap/commit/5ba48957a4afe78115ae130d63643043aff2f815))
* **cicd:** groundwork doc names its durable record, not ephemeral scratch ([9701a08](https://github.com/unified-systems-com/tap/commit/9701a085b5a08ba53a467c76d55bac2e3961b2e4))
* **cicd:** injection pre-screen shortlist from live research — PIGuard first, PG2 ensemble option, cost-raiser-not-wall doctrine ([560e9c3](https://github.com/unified-systems-com/tap/commit/560e9c35875277e2daa9610331fa0fb1486cd0c0))
* **cicd:** JS acquisition is npm ci in a pinned builder stage — not a hand-rolled fetcher ([1ec7a6e](https://github.com/unified-systems-com/tap/commit/1ec7a6e8a373339f5b3ab05db840e8fae75f2d7f))
* **cicd:** last spec-review notes — Unified brand names, injection pre-screen, out-of-band escalation, prompt packs, confidence stance ([f133fd0](https://github.com/unified-systems-com/tap/commit/f133fd056f287d1d89c86cfad74d5d19106bf1b4))
* **cicd:** plugin SBOM lane live-proven — sbom-10 Partial, pilot + rollout recorded ([4f6da80](https://github.com/unified-systems-com/tap/commit/4f6da802d199881398a0757f990309f99df52221))
* **cicd:** plugin-declared SBOMs (req-cicd-sbom-10) ([ce803be](https://github.com/unified-systems-com/tap/commit/ce803bec0069fce1c6301a05c340a2662718068d))
* **cicd:** port AI-review canon from session/sam-dev (byte-identical) ([651e2bd](https://github.com/unified-systems-com/tap/commit/651e2bd659fc5345cdbb7870d525676804a0f560))
* **cicd:** PR [#92](https://github.com/unified-systems-com/tap/issues/92) Copilot triage — live banner in copilot-instructions, full shim paths in Map ([7f10360](https://github.com/unified-systems-com/tap/commit/7f10360c5a86e0b5806fb4068f922b324ae87641))
* **cicd:** provenance-2 tightened per Codex review — bidirectional, relative-path, split semantics ([7de9d0f](https://github.com/unified-systems-com/tap/commit/7de9d0f580dcf5a8c885afa94af87a194b18a23d))
* **cicd:** re-architect AI review to two-stage fork-covering harness; seat Grok; import ToB methodology ([d56317f](https://github.com/unified-systems-com/tap/commit/d56317f34e521fedb9d5e23a3b9bae9462f5e58d))
* **cicd:** SBOM emission specification (proposed) + groundwork record ([0fa46b5](https://github.com/unified-systems-com/tap/commit/0fa46b5e3ce29ab321fd67a8613843b393730635))
* **cicd:** SBOM spec conforms to the requirement-traceability standard ([eebac51](https://github.com/unified-systems-com/tap/commit/eebac51d8668e190e6cfeed22e6e81628a055a98))
* **cicd:** SBOM spec extensible to flavored ready-made images (req-cicd-sbom-9) ([194cb3e](https://github.com/unified-systems-com/tap/commit/194cb3e5d667051cbbc41e751f7065368b5469cf))
* **cicd:** sbom-13 becomes the adopt-native-distribution doctrine ([9fcaaa7](https://github.com/unified-systems-com/tap/commit/9fcaaa71969f9e2d1fb25649a6739ea8d50a1363))
* **cicd:** supplemental entries are one schema-validated manifest format (sbom-3, P2) ([c614a81](https://github.com/unified-systems-com/tap/commit/c614a8192d8c084d30183effdeb06552d21a1994))
* **cicd:** the sbom-10 named gap is tap-build-dependencies, not the archived repo ([82e6138](https://github.com/unified-systems-com/tap/commit/82e6138a06213e9a18c3d36fa9aaade339c2231a))
* **cicd:** triage remainder — immutable scan subject + digest-form verify example ([15caa58](https://github.com/unified-systems-com/tap/commit/15caa584e745fee479e383266cfd1b7859b71fd3))
* **cicd:** uv/uvx are declared out-of-band components, not excluded noise ([d1b0169](https://github.com/unified-systems-com/tap/commit/d1b01692a61bd42700f98c6e7e1d574235cf182d))
* **cicd:** verified wheel-cache seed (req-cicd-supply-chain-provenance-2, proposed) ([53e0960](https://github.com/unified-systems-com/tap/commit/53e096057de5c39ec66234e10d6fe3269d43e4ca))
* **cicd:** visible Spec: line in the SBOM groundwork doc (req-docs-spec-linkage) ([aa541e0](https://github.com/unified-systems-com/tap/commit/aa541e084a66543d5064a8ae5861f272aba4e529))
* **cicd:** wire the dedicated harness repo into canon (req-cicd-ai-review-harness-repo) ([32d3056](https://github.com/unified-systems-com/tap/commit/32d3056294db131309cb972592279043ebcd8f30))
* **dupes:** Tier 3 decision brief — 2026-08-20 read-only evidence pass ([e121368](https://github.com/unified-systems-com/tap/commit/e1213681b310f91c6d1e76c5ca99a1eeffd2b547))

## [0.1.3](https://github.com/unified-systems-com/tap/compare/v0.1.2...v0.1.3) (2026-08-20)


### Features

* **cicd:** consumers pin a version instead of tracking :latest ([60f2093](https://github.com/unified-systems-com/tap/commit/60f2093ec7e2aab38bcaf435bb32f66e86165eff))
* **cicd:** digest-threaded publish pipeline (req-cicd-supply-chain-provenance-1) ([0c4c953](https://github.com/unified-systems-com/tap/commit/0c4c953f3c09b97a81d38bb7c66c9582cea8cc17))
* **dco:** remediation commits — certify retroactively without rewriting history ([026b1f9](https://github.com/unified-systems-com/tap/commit/026b1f9e3c6a6b957655a0e25bfc475271b7e36d))
* **grid:** EntityType.kind — discriminate node vs edge in the type catalog ([0ab001a](https://github.com/unified-systems-com/tap/commit/0ab001aeeb75073ecebe186849425ae3c2163eed))
* **health:** probe selection sets — liveness/readiness, declared and mandatory ([fdfe4c3](https://github.com/unified-systems-com/tap/commit/fdfe4c3eb21dba17824d71b9c455e7a5f8ed7169))
* **health:** serving, grid-table and plugins-loaded probes ([3394ad0](https://github.com/unified-systems-com/tap/commit/3394ad0e9eb2155b4a8e0c56556fa2296db0731b))
* **policy:** CONTRIBUTING + DCO land as approved policy; sign-off enforcement ON ([90d5a14](https://github.com/unified-systems-com/tap/commit/90d5a14ad295efd345836812a9e235b0ea9e6214))


### Bug Fixes

* **auth:** enrollment link origin IS the ceremony origin (sweep S2) ([3cca3ac](https://github.com/unified-systems-com/tap/commit/3cca3acf313cc8ca5a08d86466c1a79632c24973))
* **cicd:** base compose is pull-only — building is an explicit opt-in overlay ([fdd6139](https://github.com/unified-systems-com/tap/commit/fdd61399fe3598b246226c895b1cef6631cb09f0))
* **cicd:** CI rides tap-db:latest — the version pin is a consumer contract ([f734c2f](https://github.com/unified-systems-com/tap/commit/f734c2f2f7ed2b50ee24f6ba44433dfe9cc589f5))
* **cicd:** release-commit publishes survive newest-main-wins cancellation ([2dc00c1](https://github.com/unified-systems-com/tap/commit/2dc00c1efd89585a3d7511f500437d6c130548c1))
* nine duplicate-fact collapses + four boot/auth precision fixes ([0becf1a](https://github.com/unified-systems-com/tap/commit/0becf1a34c25d750f44c9c3f7289953da724da06))


### Documentation

* **grid:** backlog req for first-party types in the type catalog ([3a3704a](https://github.com/unified-systems-com/tap/commit/3a3704a563b9c63b4a2da3ca56fb68a014e09ab1))
* **grid:** sharpen the stale-catalog-rows gap — accumulated state, not fresh-instance behaviour ([7f75fe6](https://github.com/unified-systems-com/tap/commit/7f75fe6ea719175a302da96b01d4979b9f12013d))
* **health:** correct the entity-type catalog non-goal — measured causes, not a classification issue ([2ea3117](https://github.com/unified-systems-com/tap/commit/2ea31176ccd6f10812e17bf5c4ebbca262171830))
* **misc:** duplicate-derivation backlog — the open ~30, with the detectors ([0baae29](https://github.com/unified-systems-com/tap/commit/0baae2949357de413af44bf53cefe2309a14efac))
* **plugins:** lifecycle v1 — define the departure contract (req-plugin-lifecycle-v1-departure) ([2852990](https://github.com/unified-systems-com/tap/commit/2852990953e989e8b81d5e69e4f001b18f2bf02b))
* **policy:** correct the approval provenance recorded in 90d5a14a ([a28419b](https://github.com/unified-systems-com/tap/commit/a28419bf89fa5c951aacd86e5822157510e9022f))

## [0.1.2](https://github.com/unified-systems-com/tap/compare/v0.1.1...v0.1.2) (2026-08-12)


### Features

* **grid:** grid-table classification single source (req-grid-table-classification.sec) ([e805865](https://github.com/unified-systems-com/tap/commit/e80586571a34061c631c24312f642a18f6e7b7a7))
* **specs:** TAP-KNOWN-DUPE convention for intentional duplicates (req-tap-known-dupes) ([24767b3](https://github.com/unified-systems-com/tap/commit/24767b317fde60f7390c1d75e20d6fe6c60e46b0))


### Bug Fixes

* **auth:** built-in actor keys collapse to one code home (audit [#2](https://github.com/unified-systems-com/tap/issues/2)) ([264e899](https://github.com/unified-systems-com/tap/commit/264e899ea14801dc430a82b2d4dd0302502ec1b6))
* **auth:** request identity derived once, at the middleware (audit [#4](https://github.com/unified-systems-com/tap/issues/4)) ([a0c977a](https://github.com/unified-systems-com/tap/commit/a0c977ae0e2570c1c640a4348522d928ddfa9767))
* **secrets:** secrets-root resolution collapses to two canonical lookups (audit [#3](https://github.com/unified-systems-com/tap/issues/3)) ([b92a168](https://github.com/unified-systems-com/tap/commit/b92a168464aba25ed9930b7cb130160dd4eb9fc2))


### Documentation

* **plugins:** spec-tap-plugin-lifecycle-v1 DRAFT — transactional plugin load/update wrapper ([af77348](https://github.com/unified-systems-com/tap/commit/af77348326acd3b9991b7d78ed91df9ab96c4a01))

## [0.1.1](https://github.com/unified-systems-com/tap/compare/v0.1.0...v0.1.1) (2026-08-12)


### Features

* **grid:** edge property lanes — central hotlink check + schema-required warn mode ([871f7f7](https://github.com/unified-systems-com/tap/commit/871f7f77bdc197a4868f3572e5a775e620f404b3))


### Bug Fixes

* **boot:** TAP_PLUGINS is authoritative — collapse the two-source plugin-set race ([e4183c3](https://github.com/unified-systems-com/tap/commit/e4183c3664295f42fa9ce08d7f6cf61a52da2604))
* **cicd:** wire the release lane to the real app — tap-release-please ([d345c62](https://github.com/unified-systems-com/tap/commit/d345c627e9beaecea2d80206075f321b24989ecf))
* **ci:** gate api-fuzz boot on migrations APPLIED, not just health — the real flake root ([625ae08](https://github.com/unified-systems-com/tap/commit/625ae086017cda375c963afe02ce98a64c3847c0))
* **grid:** annotate migration functions + registry fixture — mypy ratchet clean ([8d942f9](https://github.com/unified-systems-com/tap/commit/8d942f94b1756e425453d3e47114d3d80ba308de))
* **health:** diversify readiness with a critical 'migrations' probe — the real flake fix ([b70d7f9](https://github.com/unified-systems-com/tap/commit/b70d7f93507ca0cb9e213fb82777baa9c6362f99))


### Documentation

* **dev-validation:** close the api-fuzz known-flake ledger row — two-source INSTALLED_APPS divergence, root-caused + fixed ([f242cf9](https://github.com/unified-systems-com/tap/commit/f242cf9444073833cfbb6755dacea40f6eb96307))
* **dev-validation:** correct the known-flake ledger — the real root was migrate-vs-boot, fixed by the migrations readiness probe ([d02b444](https://github.com/unified-systems-com/tap/commit/d02b444d7aceca68e701365c34bf6a3d0e010d51))
* **health:** probes-4 ACID — add migrations to the enumerated critical set ([2cbd947](https://github.com/unified-systems-com/tap/commit/2cbd94788976a7829cb8051cfa4de8338d6059e5))
* **health:** record the migrations probe in spec-tap-health-v0 — the first readiness-class probe ([3bbfa8f](https://github.com/unified-systems-com/tap/commit/3bbfa8f2d4c3e354e9e8b4161dcef051e2cd0310))
* **spec:** api-fuzz flake ESCALATED — recurred same day; investigation owned by session/unified ([cd70a1b](https://github.com/unified-systems-com/tap/commit/cd70a1beac5d59d31101109248619ec058e0f5de))
* **spec:** api-fuzz known-flake ledger — track setup-phase reds across sessions ([4b6104f](https://github.com/unified-systems-com/tap/commit/4b6104fc0ea546a89a0139454f62365337922d4c))
