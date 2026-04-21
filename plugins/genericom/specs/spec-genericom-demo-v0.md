# Genericom Demonstration Infrastructure Specification

## Philosophy

Genericom is a fictional but intentionally life-like AWS-hosted application environment used to exercise TAP visualization features, especially pan, zoom, and future alert-badge behavior. The environment is meant to feel like a real mid-scale production SaaS deployment rather than a toy diagram, while still staying constrained enough for an initial GRIFT buildout.

The v0 specification starts with the minimum AWS footprint necessary to show a believable customer request path and preserve several intentional misconfigurations that will later become findings. It does not attempt to solve finding modeling, exception handling, or host/runtime graph depth yet. Where those capabilities are needed but not yet implemented, the spec calls out follow-up work explicitly.

## Goals

|    |              |                                                                 |
| :---: | ---       | ---                                                             |
| 1. | Realistic      | Model a believable production web application stack with concrete AWS details, versions, IDs, and topology |
| 2. | Minimal        | Keep the first pass limited to the smallest useful AWS slice needed to drive visualization work |
| 3. | Expandable     | Leave clear extension points for additional AWS accounts, third parties, CI/CD, security tooling, admin paths, and AI integrations |
| 4. | Finding-Aware  | Preserve intentional misconfigurations in the written spec so they can later become findings without losing the original design intent |
| 5. | Core-Aligned   | Use AWS Core where it exists today and call out AWS Core / Computing Core follow-up work where modeling gaps remain |

## Requirements

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-genericom-demo-scope | [Environment Scope](#environment-scope) | Proposed | Defines the initial Genericom demonstration slice |
| req-genericom-demo-topology | [Production Topology](#production-topology) | Proposed | Defines the concrete AWS architecture to model first |
| req-genericom-demo-runtime | [Application Runtime Details](#application-runtime-details) | Proposed | Pins versions, classes, addresses, and operating details |
| req-genericom-demo-findings | [Intentional Future Findings](#intentional-future-findings) | Proposed | Preserves misconfiguration intent without defining finding models yet |
| req-genericom-demo-finding-stash | [Finding-Intent Stash](#finding-intent-stash) | Backlog | Machine-readable finding-intent block shipped in GRIFT; removed once first-class finding models land |
| req-genericom-demo-future | [Named Future Expansions](#named-future-expansions) | Proposed | Lists the next domains the plugin should grow into |
| req-genericom-demo-gaps | [Core Modeling Follow-Up](#core-modeling-follow-up) | Proposed | Calls out AWS Core and Computing Core work needed later |

### Environment Scope
----
RID: `req-genericom-demo-scope`
Status: `Proposed`

Genericom v0 is a single-account AWS production environment centered on one customer-facing web application.

#### Status Details

This is intentionally narrower than the eventual Genericom estate. Future accounts and platform subsystems are expected, but the first spec should stay focused on the minimum architecture needed to start building useful visualizations.

#### Implementation

The initial Genericom environment has these boundaries:

- one AWS account only
- one primary region: `us-west-1`
- two specific availability zones: `us-west-1a` and `us-west-1c`
- one public domain: `genericom.com`
- one customer-facing web application stack
- one production VPC

The first spec includes only these primary AWS components:

- Route 53 public hosted zone and apex alias records
- ACM certificate for `genericom.com`
- internet-facing ALB
- ALB target group
- two EC2 web instances running Django
- one multi-AZ RDS PostgreSQL instance
- one VPC with six subnets
- one internet gateway attached to the VPC

The first spec explicitly defers:

- additional AWS accounts
- security groups
- route tables
- NAT gateways
- autoscaling groups
- formal finding and exception models

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-genericom-demo-scope-1 | Single Account v0 | Proposed | The first written spec models a single AWS account only. | |
| req-genericom-demo-scope-2 | Minimal AWS Slice | Proposed | The first written spec includes only the minimum AWS components needed for the customer request path and network layout. | |
| req-genericom-demo-scope-3 | Explicit Deferrals | Proposed | The first written spec names the major AWS/platform capabilities that are intentionally deferred. | |

#### Future

Add shared services, security, and development accounts later as the Genericom estate grows.

### Production Topology
----
RID: `req-genericom-demo-topology`
Status: `Proposed`

The Genericom v0 production environment is an internet-facing ALB that terminates HTTPS and forwards traffic to a pair of private EC2 Django hosts, which in turn use a private multi-AZ PostgreSQL RDS backend.

#### Status Details

This requirement defines the concrete graph shape that should be used to seed the first Genericom visualization dataset.

#### Implementation

The production account is a fictional but plausible AWS account:

- account name: `genericom-prod`
- account id: `482761905314`

The primary network container is:

- VPC name: `genericom-prod-vpc`
- VPC id: `vpc-0f4e3b8c2a1d9e76b`
- VPC ARN: `arn:aws:ec2:us-west-1:482761905314:vpc/vpc-0f4e3b8c2a1d9e76b`
- CIDR: `10.0.0.0/16`

The internet gateway attached to the VPC is:

- IGW name: `genericom-prod-igw`
- IGW id: `igw-0a3f82b71c6d4e519`
- IGW ARN: `arn:aws:ec2:us-west-1:482761905314:internet-gateway/igw-0a3f82b71c6d4e519`
- attached VPC: `genericom-prod-vpc`

The six subnets are:

| Name | Subnet ID | ARN | AZ | CIDR | Tier |
| --- | --- | --- | --- | --- | --- |
| `genericom-prod-public-alb-a` | `subnet-07c1a2f4e8b63d101` | `arn:aws:ec2:us-west-1:482761905314:subnet/subnet-07c1a2f4e8b63d101` | `us-west-1a` | `10.0.0.0/24` | public ALB |
| `genericom-prod-public-alb-c` | `subnet-01b8d7ce4f922aa34` | `arn:aws:ec2:us-west-1:482761905314:subnet/subnet-01b8d7ce4f922aa34` | `us-west-1c` | `10.0.1.0/24` | public ALB |
| `genericom-prod-private-web-a` | `subnet-0d92c6b4a17ef8102` | `arn:aws:ec2:us-west-1:482761905314:subnet/subnet-0d92c6b4a17ef8102` | `us-west-1a` | `10.0.10.0/24` | private web |
| `genericom-prod-private-web-c` | `subnet-0aa53ef819c274d66` | `arn:aws:ec2:us-west-1:482761905314:subnet/subnet-0aa53ef819c274d66` | `us-west-1c` | `10.0.11.0/24` | private web |
| `genericom-prod-private-db-a` | `subnet-02ce59ab417ed9f42` | `arn:aws:ec2:us-west-1:482761905314:subnet/subnet-02ce59ab417ed9f42` | `us-west-1a` | `10.0.20.0/24` | private database |
| `genericom-prod-private-db-c` | `subnet-0619de74bc3285af1` | `arn:aws:ec2:us-west-1:482761905314:subnet/subnet-0619de74bc3285af1` | `us-west-1c` | `10.0.21.0/24` | private database |

The DNS layer is:

- hosted zone name: `genericom.com`
- hosted zone id: `Z08451273GENERICOM9Q2`
- hosted zone ARN: `arn:aws:route53:::hostedzone/Z08451273GENERICOM9Q2`
- apex records:
  - `A` alias for `genericom.com`
  - `AAAA` alias for `genericom.com`

The apex records target the ALB:

- ALB name: `genericom-prod-web-alb`
- ALB ARN: `arn:aws:elasticloadbalancing:us-west-1:482761905314:loadbalancer/app/genericom-prod-web-alb/3c7f5b92d1e84aa1`
- ALB DNS name: `genericom-prod-web-alb-184472991.us-west-1.elb.amazonaws.com`
- scheme: internet-facing
- public listeners:
  - `HTTP :80` with explicit redirect behavior to `HTTPS :443`
  - `HTTPS :443` with ACM-backed TLS termination

The certificate layer is:

- ACM certificate name: `genericom-prod-genericom-com-cert`
- ACM certificate ARN: `arn:aws:acm:us-west-1:482761905314:certificate/98c40b84-f6ad-4e8c-b6d3-87b93f7112c4`
- subject: `genericom.com`
- relative age: about 11 months old

The ALB forwards to one target group:

- target group name: `genericom-prod-web-tg`
- target group ARN: `arn:aws:elasticloadbalancing:us-west-1:482761905314:targetgroup/genericom-prod-web-tg/c2f96b8d70a4e2f1`
- protocol: `HTTP`
- port: `80`
- target type: `instance`
- health check: intentionally left unspecified in v0

The two web instances are:

| Name | Instance ID | ARN | AZ | Subnet | Private IP | Public IP |
| --- | --- | --- | --- | --- | --- | --- |
| `genericom-prod-web-a` | `i-0b7d5a1c8e44f2193` | `arn:aws:ec2:us-west-1:482761905314:instance/i-0b7d5a1c8e44f2193` | `us-west-1a` | `genericom-prod-private-web-a` | `10.0.10.21` | none |
| `genericom-prod-web-c` | `i-03f2ce198bd47aa60` | `arn:aws:ec2:us-west-1:482761905314:instance/i-03f2ce198bd47aa60` | `us-west-1c` | `genericom-prod-private-web-c` | `10.0.11.21` | none |

The database instance is:

- RDS instance name: `genericom-prod-postgres`
- DB instance identifier: `genericom-prod-postgres`
- RDS ARN: `arn:aws:rds:us-west-1:482761905314:db:genericom-prod-postgres`
- engine: `postgres`
- port: `5432`
- deployment: multi-AZ primary/standby
- primary AZ: `us-west-1a`
- standby AZ: `us-west-1c`
- DB subnet group behavior: spans `genericom-prod-private-db-a` and `genericom-prod-private-db-c`
- writer endpoint: `genericom-prod-postgres.c9m2a1xk0wus.us-west-1.rds.amazonaws.com`
- observed private writer address at capture time: `10.0.20.44`
- observed private standby address at capture time: `10.0.21.44`
- public accessibility: disabled

The request and dependency path is:

1. A customer resolves `genericom.com`
2. Route 53 returns dual-stack apex alias answers pointing to the ALB
3. The ALB accepts public `HTTP :80` and redirects to `HTTPS :443`
4. The ALB terminates TLS on `HTTPS :443`
5. The ALB forwards traffic internally to `genericom-prod-web-tg` over `HTTP :80`
6. The target group forwards to the two private EC2 web instances
7. The Django application on both instances listens on `TCP :80`
8. The Django application uses PostgreSQL on `TCP :5432`
9. The database backend is the private RDS instance `genericom-prod-postgres`

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-genericom-demo-topology-1 | Concrete Regional Layout | Proposed | The spec pins one region, two specific AZs, one VPC, and six subnets with exact CIDRs. | |
| req-genericom-demo-topology-2 | Concrete DNS and ALB | Proposed | The spec pins the hosted zone, apex alias records, ALB identity, and listener behavior. | |
| req-genericom-demo-topology-3 | Private Web Tier | Proposed | The spec states both EC2 web instances are private-only and includes concrete private IPs. | |
| req-genericom-demo-topology-4 | Multi-AZ Database | Proposed | The spec states the RDS PostgreSQL backend is multi-AZ primary/standby and private-only. | |
| req-genericom-demo-topology-5 | Internet Gateway Attached | Proposed | The spec pins an internet gateway attached to the production VPC. | |

#### Future

Add NAT, route tables, and security groups as a follow-on network-expansion pass.

### Application Runtime Details
----
RID: `req-genericom-demo-runtime`
Status: `Proposed`

The Genericom runtime specification should pin concrete but slightly stale software versions and instance classes so the environment feels lived-in rather than freshly provisioned.

#### Status Details

This requirement exists to make the demonstration dataset feel like a real operator-owned environment with recognizable choices and version lag.

#### Implementation

The two web instances are intentionally identical for v0:

- instance class: `m6i.2xlarge`
- operating system: Amazon Linux 2023
- pinned OS release: `2023.5.20240916`
- web framework: Django
- pinned Django version: `5.1.3`
- cryptography library present on-host: OpenSSL
- pinned OpenSSL version: `3.0.12`
- application listen port: `80/tcp`
- relative age: about 9 months old

The RDS instance is:

- instance class: `db.r6i.2xlarge`
- engine: PostgreSQL
- pinned PostgreSQL version: `16.4`
- logical database name used by Django: `genericom_app`
- encryption at rest: disabled
- relative age: about 14 months old

The application-to-database relationship is direct:

- the Django application on each EC2 instance uses the RDS PostgreSQL instance as its primary database backend
- the logical database inside PostgreSQL is `genericom_app`

The runtime spec intentionally does not pin:

- security group rules
- ALB health check path
- package manager provenance beyond the version facts above
- autoscaling behavior

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-genericom-demo-runtime-1 | Exact Versions Pinned | Proposed | The spec pins exact versions for Amazon Linux 2023, Django, PostgreSQL, and OpenSSL. | |
| req-genericom-demo-runtime-2 | Exact Classes Pinned | Proposed | The spec pins exact EC2 and RDS instance classes. | |
| req-genericom-demo-runtime-3 | Database Name Pinned | Proposed | The spec pins the logical PostgreSQL database name used by Django. | |

#### Future

When Computing Core exists, extend the runtime portion from OS/library facts into explicit host, file, library, and runtime graph objects.

### Intentional Future Findings
----
RID: `req-genericom-demo-findings`
Status: `Proposed`

The spec must preserve several intentional misconfigurations as future findings, even though v0 does not yet define finding objects or exception handling behavior.

#### Status Details

This requirement is important because the demonstration environment is intentionally not pristine. The architecture itself should retain those conditions so future control and signal work has concrete material to attach to.

#### Implementation

The following conditions are intentionally present and should later become findings:

- the ALB exposes public `HTTP :80`, even though that listener redirects to `HTTPS :443`
- the ALB forwards to the web tier over unencrypted `HTTP :80`
- both web instances effectively serve the application on `TCP :80`
- the RDS PostgreSQL instance has encryption at rest disabled

The spec is intentionally not defining in v0:

- a finding entity type
- a finding severity taxonomy
- an exception entity type
- exception approval or expiry logic
- signal/badge wiring

The key requirement is preservation of intent:

- these conditions must be written down clearly
- future work must not “clean them up” accidentally when the first GRIFT or plugin implementation is created

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-genericom-demo-findings-1 | Public Port 80 Preserved | Proposed | The spec preserves public ALB `:80` exposure as a future finding candidate. | Redirect behavior does not erase the finding intent. |
| req-genericom-demo-findings-2 | Internal HTTP Preserved | Proposed | The spec preserves ALB-to-EC2 `HTTP :80` as a future finding candidate. | |
| req-genericom-demo-findings-3 | Unencrypted RDS Preserved | Proposed | The spec preserves disabled RDS at-rest encryption as a future finding candidate. | |
| req-genericom-demo-findings-4 | No Finding Model Yet | Proposed | The spec explicitly avoids defining finding or exception models in v0. | |

#### Future

Add first-class finding, exception, and signal models in a separate follow-on push rather than mixing them into the infrastructure spec.

### Finding-Intent Stash
----
RID: `req-genericom-demo-finding-stash`
Status: `Backlog`

Until first-class finding models exist, the Genericom GRIFT seed ships a machine-readable finding-intent block inside the `_reserved` object so future tooling can rediscover the intentional misconfigurations without re-reading the spec.

#### Status Details

This is a temporary scaffold. Its only job is to preserve the linkage between "we said this was a planned finding" and "here is the concrete entity that carries the condition." It is not an attempt at a finding model — it has no severity, no state, no lifecycle.

#### Implementation

Each GRIFT file that defines nodes carrying future-finding conditions includes a `_reserved.finding_intent` entry shaped roughly as:

```json
"finding_intent": [
  {
    "slug": "genericom-alb-public-http-80",
    "target_entity_id": "<alb-entity-id>",
    "summary": "ALB exposes public HTTP :80 listener (redirects to :443 but still publicly reachable).",
    "spec_ref": "req-genericom-demo-findings-1"
  }
]
```

Required fields:

- `slug` — stable short identifier for the intent
- `target_entity_id` — the `entity_id` of the node the intent attaches to
- `summary` — human-readable one-liner
- `spec_ref` — ACID this intent was promised in

The v0 finding intents are:

- `genericom-alb-public-http-80` → ALB (`req-genericom-demo-findings-1`)
- `genericom-alb-internal-http` → target group / ALB-to-EC2 path (`req-genericom-demo-findings-2`)
- `genericom-rds-unencrypted-at-rest` → RDS instance (`req-genericom-demo-findings-3`)

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-genericom-demo-finding-stash-1 | Intent Block Present | Backlog | GRIFT files shipping finding-bearing nodes include a `_reserved.finding_intent` array with one entry per intentional misconfiguration. | |
| req-genericom-demo-finding-stash-2 | Intents Link To Entities | Backlog | Each finding-intent entry references an `entity_id` that exists in the same GRIFT document. | |
| req-genericom-demo-finding-stash-3 | Intents Link To Spec | Backlog | Each finding-intent entry cites the acceptance-criterion ID from `req-genericom-demo-findings` it preserves. | |
| req-genericom-demo-finding-stash-4 | Stash Removed When Findings Land | Backlog | When first-class finding entities exist and Genericom's intents have been promoted to real findings, this requirement and its `_reserved.finding_intent` blocks are deleted from the plugin. | Removal itself closes out this requirement. |

#### Future

Delete this entire section, its ACIDs, and every `_reserved.finding_intent` block from Genericom's GRIFT files once first-class finding models exist and the three v0 conditions have been represented as real finding entities.

### Named Future Expansions
----
RID: `req-genericom-demo-future`
Status: `Proposed`

The Genericom spec should explicitly name the next domains to expand after the base AWS architecture is in place.

#### Status Details

These are placeholders for later design work, not v0 implementation requirements.

#### Implementation

Future third-party integrations:

- Stripe
- SendGrid
- Splunk

Future CI/CD components:

- GitHub Actions
- ECR

Future remote administration components:

- SSM Session Manager
- bastionless remote administration path

Future security tooling components:

- GuardDuty
- Security Hub
- Tenable self-hosted on EC2
- Trend Micro self-hosted on EC2

Future AI integrations:

- Bedrock
- OpenAI API

Future infrastructure/platform additions:

- autoscaling group for the web tier
- additional AWS accounts beyond production

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-genericom-demo-future-1 | Named Expansion Areas | Proposed | The spec explicitly names the major future expansion categories. | |
| req-genericom-demo-future-2 | Example Components Listed | Proposed | Each named expansion area includes at least one or two example components. | |

#### Future

As these areas are designed, promote them into their own dedicated Genericom sub-specifications.

### Core Modeling Follow-Up
----
RID: `req-genericom-demo-gaps`
Status: `Proposed`

The Genericom spec depends on several modeling capabilities that do not yet fully exist in TAP core plugins.

#### Status Details

These gaps should be treated as explicit follow-up work rather than papered over with ad hoc Genericom-only stopgaps.

#### Implementation

AWS Core follow-up needed:

- add Route 53 record-level modeling so the apex `A` and `AAAA` alias records for `genericom.com` can be represented directly instead of only as hosted zone configuration detail

Computing Core follow-up needed:

- add host modeling sufficient to represent runtime placement on a machine
- add file modeling sufficient to represent on-host artifacts
- add library modeling sufficient to represent cryptographic libraries and similar dependencies
- add runtime/process/program relationships sufficient to connect the Django application to host-level dependencies
- allow `port_number = null` in core networking to represent ephemeral ports

The Genericom host/runtime slice should eventually be able to express ideas like:

- a host contains runtime artifacts
- a runtime depends on a library
- a library or file participates in cryptographic behavior

This spec intentionally does not define those node or edge types itself.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-genericom-demo-gaps-1 | AWS Core Follow-Up Named | Proposed | The spec explicitly identifies Route 53 record-level modeling as an AWS Core follow-up. | |
| req-genericom-demo-gaps-2 | Computing Core Follow-Up Named | Proposed | The spec explicitly identifies host/file/library/runtime modeling as a Computing Core follow-up. | |
| req-genericom-demo-gaps-3 | Ephemeral Port Follow-Up Named | Proposed | The spec explicitly identifies nullable `port_number` for ephemeral ports as a core networking follow-up. | |

#### Future

Revisit this section after AWS Core and Computing Core advance enough to support a richer Genericom runtime and DNS model.
