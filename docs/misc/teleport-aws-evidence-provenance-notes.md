# Teleport as Audited Access Path + Cryptographic Evidence Provenance

Captured 2026-06-30 from a design discussion. This is a thinking document — not a
spec, not an ADR, not scheduled work. Its purpose is to preserve a line of
reasoning about (a) how Rampart would consume a customer's Teleport deployment as
the access path to their AWS accounts via the existing `aws_core` boto plugin,
and (b) a stronger, longer-horizon idea for making collected AWS evidence
*tamper-evident to an adversarial relying party*. The evidence-provenance half is
explicitly **not on the mid-July critical path** — it depends partly on a vendor
roadmap and on attestation we don't have yet. It is written down so it isn't lost.

Context: assessments run in the **FedRAMP 20x** setting. Rampart accesses a
company's internals and AWS accounts through Teleport, pulls data back onto the
grid, and validates their positioning against KSIs (system / network /
application graphs). GitHub access is assumed separate (its own GitHub App,
its own audit log). The threat actor that motivates the second half is the
**assessor itself** — i.e. the relying party (FedRAMP PMO / agency / 3PAO)
assumes *we* might doctor AWS responses to flatter (or fail) a posture, and we
want to defeat that accusation.

## TL;DR

- **Integration is nearly free.** Teleport's AWS access doesn't hand out keys; it
  stands up a **local forwarding proxy** and points the AWS SDK at it via
  `HTTPS_PROXY` + `AWS_CA_BUNDLE` + ephemeral local creds. botocore honors all
  three natively, so `aws_core` routes through Teleport with ~no code change.
- **Use Machine ID (`tbot`), not interactive `tsh`,** for assessment collectors —
  an `application-tunnel` output keeps short-lived certs auto-renewed so long
  sweeps don't die mid-run.
- **One change worth making to `aws_core`:** build boto sessions
  *credential-source-agnostic*, and scope the Teleport interception CA to the boto
  client (`verify=<bundle>`), **not** a global `AWS_CA_BUNDLE` env — don't let
  Teleport's MITM CA cover unrelated TLS in the container. (Cheap, foundational
  security edge; lay it while touching the credential plumbing.)
- **Auditability, honest version:** Teleport's audit log records the *request*
  (method, path, service/region, assumed role ARN, status, session id) — **not**
  response bodies (DynamoDB is a noted exception that records request body).
  CloudTrail independently records the call from AWS's side. The grid holds the
  responses. The valuable third-party artifact is "every call we made is
  accounted for and was read-only," not a verbatim response recording.
- **Stitch provenance:** stamp the Teleport session id (+ account + assumed role)
  into each GRIFT batch so grid provenance points at the exact Teleport audit
  event. Three independent logs agreeing (Teleport request, CloudTrail, grid) is
  itself hard to forge.
- **The "prove the response is genuine" problem is a non-repudiation problem, and
  TLS does not solve it.** See below — it's the crux.

## Part 1 — Consuming Teleport as the AWS access path

### Mechanism
- `tsh apps login <aws-app> --aws-role <ARN>` then `tsh proxy aws -p <port>` emits:
  - `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` — ephemeral, local-only dummies
    the local proxy recognizes
  - `AWS_CA_BUNDLE` — path to Teleport's interception CA
  - `HTTPS_PROXY=http://127.0.0.1:<port>`
- The local proxy terminates TLS, inspects the SigV4 request, then the Teleport
  **app-service** re-signs with the real assumed-role creds and forwards to AWS.
  The TLS interception is also *how it can audit*.
- M2M equivalent: `tbot` daemon with an `application-tunnel` service = the same
  local proxy, with auto-renewing credentials.

### Rampart topology
- A `tbot` sidecar holds the Teleport identity and exposes one local tunnel
  **per (AWS account, IAM role)** pair. Assessment spans many accounts; Teleport
  models each as an "app" (or one app with multiple `aws_role_arns`).
- Customer grants a Teleport role whose `aws_role_arns` lists **read-only** IAM
  roles only (`SecurityAudit` + `ViewOnlyAccess`, or a custom assessment policy).
  Protects both sides — we cannot mutate even by accident.
- Rampart config carries `account_id -> {teleport_app, role_arn, proxy_url}`; the
  collector selects the right proxy per account (botocore proxy config is
  per-client).
- **No long-lived AWS keys anywhere in Rampart or on the grid.** Teleport creds
  are short-lived + externally brokered — matches the secrets posture
  (per-consumer health probe = "is the tbot tunnel healthy?", not an on-grid
  SecretReference).

### Open compatibility/placement questions
- Verify the specific services collectors hit behave through the proxy (S3
  virtual-host addressing, STS chaining, streaming/presigned URLs).
- Confirm whether the customer's Teleport→IAM setup propagates a session identity
  tag into CloudTrail (strengthens attribution from "the shared assessment role"
  to "our specific Teleport user").
- Multi-account fan-out = N local tunnels; the collector→proxy mapping must be
  config-driven and discoverable.

### Two distinct roles for Teleport — keep them separate in the narrative
1. **The customer's production access plane** = *evidence we collect* and validate
   against KSIs (phishing-resistant MFA, least privilege, JIT, session recording
   → KSI-IAM, KSI-MLA).
2. **Our assessment access path** = a *strength of the methodology*: every byte of
   evidence pulled over short-lived, MFA-gated, least-privilege, fully-audited,
   read-only access. A strong answer to "how do we trust the assessor's
   collection?" — increasingly relevant as 20x pushes toward machine-collected,
   continuously-validated evidence.

## Part 2 — Making collected responses tamper-evident (the long game)

Goal: defeat *"you modified the AWS response to make their posture look different
than it really is."* The relying party treats **us** as potentially adversarial.

### Why the obvious moves don't work
- **A custom-compiled `tbot` fork we build and run proves nothing.** It just moves
  the objection from "you doctored the response" to "you doctored the recorder."
  The recorder must be trusted by the relying party and untamperable by us.
- **TLS gives integrity-in-transit, not non-repudiation.** Session keys are held
  by *both* endpoints, so a TLS transcript we keep is forgeable by us after the
  fact — it is not third-party-verifiable proof that "AWS said X." AWS signs the
  *request* (SigV4); it does **not** sign responses in a presentable form. So
  MITM-recording the response, by itself, yields an artifact with no
  non-repudiation value: our word in a different file format.

### The refined idea (good, with one surviving gap)
Convince **Teleport (the vendor)** to add response recording, ship it in the
official **signed** container, deploy it unmodified, and have it **emit hashes**
of response content (not full copies) to an out-of-bounds sink. We keep the full
response on the grid; validation = recompute `H(response)` over the grid copy and
compare to the emitted hash.

What this fixes:
- **Vendor-signed image kills the "modified recorder" objection** — verify the
  image digest against Teleport's signature (cosign/Sigstore). Trust anchored in a
  party with no stake in the assessment outcome.
- **Hashing kills the "secondary store of responses" concern** and gives a tiny,
  clean tamper-evidence primitive.

The surviving gap — **signing proves the binary, not the runtime**:
- On a host **we** control (root, `ptrace`, `/proc/<pid>/mem`, eBPF, malicious
  hypervisor, swapped CA trust store), we can tamper a signed binary's **inputs
  and memory at runtime**. An honest signed recorder will faithfully hash whatever
  bytes are presented to it — so the accusation mutates once more to *"you fed the
  recorder a forged response before it hashed it"* (MITM your own proxy's egress,
  or tamper the trust store so a fake AWS cert validates). Image signing ≠ runtime
  integrity.

### The fix is placement, not just signing
Teleport's architecture hands you the placement for free: the **app-service** (not
the local tbot tunnel) holds the IAM role, terminates TLS *to AWS*, and receives
the response.
- **Hash at the app-service, operated by someone who isn't us** (customer / neutral
  party / Teleport Cloud). Then both the binary (signed) *and* the runtime
  (someone else's host) are outside our control, and the TLS-to-AWS endpoint is
  theirs — so `H(response)` genuinely attests to *what AWS sent*, not merely *what
  reached our proxy*.
- **If it must run on our host**, a signature is insufficient; you need **remote
  attestation** (AWS Nitro Enclave / measured boot) so the relying party verifies
  the runtime, not just the artifact. (Converges with the attested-enclave
  collector idea.)

So the feature ask to Teleport is not "record/hash responses" — it is **"hash
responses at the app-service and emit to an external append-only sink,"** because
the *placement* carries the trust.

### Two more required edges
- **The hash sink must be append-only and out of our unilateral control** — a
  transparency-log / WORM store with third-party witnessing and independent
  timestamping, not "a different bucket we own." Otherwise we can selectively
  delete inconvenient hashes or backdate entries.
- **Hashes prove integrity, not completeness.** We could simply never run the
  embarrassing query, or drop a response before it's hashed. The defense is
  **reconciliation against the independent request logs**: every request in
  Teleport's request events + CloudTrail must have a corresponding hash in the
  transparency log and a node on the grid. Coverage is proven by cross-referencing
  the witnesses, not by the hashes themselves.

### Heavier alternative (reserve)
**TLSNotary / DECO / zkTLS** — a notary co-participates in the TLS handshake
holding a share of the session keys, so the transcript is provably authentic and
the client cannot have forged it. This is the actual cryptographic answer to
"prove AWS said X," but the tooling is immature for arbitrary AWS API traffic.
Reserve for a relying party that explicitly demands cryptographic non-repudiation
and won't accept attestation.

## Strategic posture (center-of-gravity check)

- **Ships now (defensible-today evidence):** for the load-bearing KSIs, prefer
  **AWS-native, relying-party-owned sources of record** — **AWS Config**
  (point-in-time resource config history), **Security Hub**, **CloudTrail** —
  delivered into an account the relying party controls. The cheapest way to defeat
  "you doctored it" is to collect the decisive evidence from a source where we were
  never in a position to doctor it. Live API collection through Teleport becomes
  enrichment rather than the load-bearing attestation.
- **Forward bet (partner / R&D thread):** "cryptographic evidence provenance for
  audited cloud access" is a compliance feature with a 20x tailwind, and a vendor
  with audit/compliance customers has reason to want it. A widely-deployed,
  vendor-maintained, signed recorder hashing at an app-service we don't operate is
  far more credible to a 3PAO than anything bespoke. Hold it as a deliberate
  forward bet and a possible Teleport co-development conversation — **not** as
  blocking work for launch.

## Pointers
- Teleport AWS app access: https://goteleport.com/docs/enroll-resources/application-access/cloud-apis/aws-console/
- Teleport Machine ID + Application Access: https://goteleport.com/docs/machine-workload-identity/machine-id/access-guides/applications/
- Teleport audit event reference: https://goteleport.com/docs/reference/audit-events/
- Related thinking: [Agent-Affordance Laws](agent-affordance-laws.md) (audit trails / authority declarations for programmatic actors); the secrets-conditional-validation posture (per-consumer health probes).
