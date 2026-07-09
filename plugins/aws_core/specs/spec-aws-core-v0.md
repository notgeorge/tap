# AWS Core Plugin Specification

## Philosophy

The AWS Core plugin provides the foundational resource-type models needed to represent a modern AWS cloud application inside TAP's graph. The plugin favors granularity over abstraction — each AWS resource type that matters for security, compliance, or operations is its own model with typed fields, rather than a generic "cloud resource" blob. This makes the graph queryable, the edges meaningful, and the visualization useful.

The plugin deliberately models resource types, not the AWS service catalog itself. EC2 Instance, S3 Bucket, and VPC are resource types that exist in a running AWS account. "Amazon EC2" as a product page on aws.amazon.com is not modeled — it has no state to track and no edges to traverse.

v0 is intentionally scoped to the "meat and potatoes" AWS resources common to most major infrastructures. The plugin is designed to grow as new resource types prove necessary, with a catalog refresh skill that can detect and propose additions.

## Goals

|    |              |                                                                 |
| :---: | ---       | ---                                                             |
| 1. | Granular      | Each resource type is its own model with typed fields and a configuration JSONField for full metadata |
| 2. | Queryable     | Key fields (instance IDs, ARNs, states) are indexed Django fields, not buried in JSON |
| 3. | Connected     | Semantically meaningful edge types express security, operational, and structural relationships |
| 4. | Refreshable   | Reference data (regions, AZs) is maintained by an automated catalog refresh skill |
| 5. | Portable      | The plugin lives in its own git repo and integrates into TAP as a git submodule |

## Requirements

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-aws-core-scope | [Plugin Scope](#plugin-scope) | Implemented | Defines what the plugin covers and excludes |
| req-aws-core-models | [Resource-Type Models](#resource-type-models) | Implemented | Typed resource-type models; manifest is the canonical inventory |
| req-aws-core-fields | [Field Design](#field-design) | Implemented | Hybrid typed fields + configuration JSONField |
| req-aws-core-edges | [Edge Types](#edge-types) | Implemented | Semantic edge vocabulary; manifest is the canonical inventory |
| req-aws-core-reference | [Reference Data](#reference-data) | Implemented | Regions and AZs as GRIFT seed data |
| req-aws-core-icons | [Icon Assets](#icon-assets) | Implemented | SVG icons per the TAP grid icon spec |
| req-aws-core-computing-core | [Computing Core Alignment](#computing-core-alignment) | Proposed | Future AWS-to-generic mapping belongs here rather than in `computing_core` |
| req-aws-core-validation | [Plugin Validation](#plugin-validation) | Implemented | Passes TAP plugin validation at all three levels |
| req-aws-core-nongoals | [v0 Non-Goals](#v0-non-goals) | Proposed | Explicitly deferred concerns |

### Plugin Scope
----
RID: `req-aws-core-scope`
Status: `Implemented`

The AWS Core plugin models the resource types needed to represent a running AWS cloud environment.

#### Implementation

The plugin covers:

- compute resources (EC2, Lambda, ECS, EKS)
- container infrastructure (ECR)
- storage (S3, EBS)
- databases (RDS, DynamoDB, ElastiCache, Elasticsearch/OpenSearch)
- networking (VPC, Subnet, Security Group, Network ACL, Internet Gateway, NAT Gateway, Elastic IP, Route Table, ALB, ELB, Target Group, Route 53, Network Firewall)
- identity and access (IAM User, IAM Role, IAM Policy, IAM OIDC Provider)
- security and configuration (ACM Certificate, Secrets Manager, SSM Parameter Store)
- AI services (Bedrock, SageMaker)
- infrastructure reference (Region, Availability Zone, Account)

The plugin excludes GovCloud and China partition regions from its reference data.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-aws-core-scope-1 | Resource Type Granularity | Implemented | Each AWS resource type is modeled as its own TAP model, not a generic cloud resource. | |
| req-aws-core-scope-2 | Commercial Regions Only | Implemented | Reference data covers standard commercial AWS regions; GovCloud and China partitions are excluded. | |
| req-aws-core-scope-3 | Common Infrastructure Focus | Implemented | v0 covers resource types common to most major AWS deployments. | |

#### Future

Expand to include additional services as they prove necessary for security, compliance, or operations use cases. CloudFront, WAF, CloudWatch, SNS/SQS, Step Functions, and API Gateway are likely candidates. The catalog refresh skill should detect and propose additions.

### Resource-Type Models
----
RID: `req-aws-core-models`
Status: `Implemented`

The plugin declares TAP-managed resource-type models organized by category. The
plugin manifest (`tap-plugin.toml`) is the authoritative inventory and
`validate_plugin` enforces that every declared model loads and creates — the
spec documents the categories, not a frozen count (a count is derived state that
drifts on every model added; the manifest + validator own "which models exist").

#### Implementation

| Category | Models |
| --- | --- |
| Infrastructure | AwsRegion, AvailabilityZone, AwsAccount |
| Compute | Ec2Instance, LambdaFunction, EcsCluster, EcsService, EcsTask, EksCluster |
| Containers | EcrRepository |
| Storage | S3Bucket, EbsVolume |
| Database | RdsInstance, DynamoDbTable, ElasticsearchDomain, ElasticacheCluster |
| Networking | Vpc, Subnet, SecurityGroup, NetworkAcl, InternetGateway, NatGateway, ElasticIp, RouteTable, Alb, Elb, TargetGroup, Route53HostedZone, NetworkFirewall, CloudfrontDistribution |
| Identity/Security | IamUser, IamRole, IamPolicy, AcmCertificate, SecretsManagerSecret, SsmParameter |
| AI | BedrockModel, SagemakerEndpoint |
| Observability | CloudwatchLogGroup |
| Integration | EventbridgeRule |

All models follow the TAP BaseModel contract with `ENTITY_TYPE`, `ENTITY_NAME`, `ENTITY_DESCRIPTION`, `ENTITY_ICON`, `FIELD_CRUD_SCHEMA`, `FIELD_VALIDATION_SCHEMA`, and `CREATE_REQUIRED`.

#### Known Constraints

The Django field name `instance_type` collides with `django-simple-history`'s `HistoricalRecord.instance_type` internal attribute. Models that would naturally use `instance_type` must use an alternative name:

- `Ec2Instance` uses `ec2_type`
- `ElasticsearchDomain` uses `node_type`
- `SagemakerEndpoint` uses `endpoint_instance_type`

This is a django-simple-history limitation, not a TAP design choice. The collision was detected by the plugin validation system's `runs` level.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-aws-core-models-1 | Manifest-Canonical Inventory | Implemented | Models are declared in `tap-plugin.toml` and enforced by `validate_plugin` (every declared model loads and `create_node` succeeds). The spec documents categories, not a frozen count. | Replaces the prior "N models declared" census — derived state that drifted on every add. |
| req-aws-core-models-2 | BaseModel Contract | Implemented | All models follow TAP's BaseModel contract. | |
| req-aws-core-models-3 | History Tracking | Implemented | All models inherit automatic history tracking via django-simple-history. | |
| req-aws-core-models-4 | Collector Demo Models | Implemented | CloudfrontDistribution, CloudwatchLogGroup, EventbridgeRule added for the boto3 collector demo (see `spec-aws-core-collector-v0.md` req-aws-collector-model-deps). | Migration 0002; validate_plugin `runs` PASS; aws_core suite 15/15. |

#### Future

New models should be added through the catalog refresh skill when new AWS resource types become relevant to security, compliance, or operations tracking.

### Field Design
----
RID: `req-aws-core-fields`
Status: `Implemented`

Each model uses a hybrid approach: key typed fields for queryable data, plus a `configuration` JSONField for the full metadata payload.

#### Implementation

Every AWS resource model has:

- **Key typed fields** — the most important attributes for querying, filtering, and display. These are indexed Django fields (CharField, IntegerField, BooleanField, GenericIPAddressField). Examples: `instance_id`, `vpc_id`, `engine`, `status`, `encrypted`.
- **`configuration` JSONField** — stores the complete resource configuration as received from AWS. This allows the graph to carry full metadata without requiring schema changes for every new attribute AWS adds.
- **`tags` JSONField** — the resource's AWS tags as a canonical flat `{str: str}` map, with the **same field name and shape on every `aws_core` model** so a cross-resource tag query ("everything `Owner=X` across `aws_*`") works by convention. Default `dict`, blank; populated by the collector (`spec-aws-core-collector-v0.md` `req-aws-collector-tags`), which normalizes AWS's varied tag wire shapes. It is deliberately **not** an Entity-spine facet — `dimensions` is the spine's key/value system and owns scoping; AWS tags are mutable source-owned descriptive metadata and must never re-partition the grid. v0 implements the field on the 8 manifest-collected models; rolling it onto the remaining uncollected models is a tracked mechanical follow-up (the contract is family-wide; the v0 *implementation* is scoped to what the collector populates).
- **`name` field** — human-readable name, typically from the AWS Name tag or resource display name.

The `FIELD_CRUD_SCHEMA` (service layer) and `FIELD_VALIDATION_SCHEMA` (validation layer with `validation`/`schema` wrappers) both declare every field. Nullable fields use `{"type": ["integer", "null"]}` or `{"type": ["string", "null"]}`.

`CREATE_REQUIRED` is set to the minimum fields that meaningfully identify a resource — typically the AWS resource ID (e.g. `instance_id`, `vpc_id`) or `name`.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-aws-core-fields-1 | Hybrid Field Approach | Implemented | Key typed fields for queries plus configuration JSONField for full metadata. | |
| req-aws-core-fields-2 | Dual Schema Declaration | Implemented | Both FIELD_CRUD_SCHEMA and FIELD_VALIDATION_SCHEMA are declared on every model. | |
| req-aws-core-fields-3 | Nullable Fields Correct | Implemented | Fields using `null=True` on the Django model declare nullable types in their schemas. | |
| req-aws-core-fields-4 | Canonical Tags Field | In Development | Every `aws_core` resource model declares a `tags` JSONField — canonical flat `{str:str}`, default empty, uniform name+shape across the family; collector-populated; never an Entity-spine facet. | 2026-05-19: implemented for the 8 manifest-collected models (migration 0003); the remaining ~32 uncollected models are a tracked mechanical rollout (no behavior change) — board follow-up. |

#### Future

Consider adding `"default"` values to `FIELD_CRUD_SCHEMA` entries to support a "create with just a name" workflow. This is a TAP-wide discussion, not plugin-specific.

### Edge Types
----
RID: `req-aws-core-edges`
Status: `Implemented`

The plugin declares a semantic edge vocabulary organized by relationship
category. The plugin manifest (`tap-plugin.toml`) is the authoritative inventory
and `validate_plugin` enforces that every declared edge loads and `create_edge`
succeeds for constrained types — the spec documents the categories and the
naming convention, not a frozen count (a count is derived state that drifted on
every edge added; the manifest + validator own "which edges exist").

#### Implementation

Edge slugs follow the consolidated naming convention canonical in
`tap_grid/skills/add-edge/SKILL.md`: mechanical-not-philosophical;
`<ACTION>_<OBJECT>`; the edge points in the direction of action initiation;
`_TO` is never used (forward is unmarked); `_FROM` is reserved for a
data-backwards edge (data flows opposite the action/edge direction); and
locative/relational prepositions (e.g. `FEDERATES_INTO`) keep their inherent
preposition. Lineage: `e5229d4` renamed terse predicates to explicit
`<ACTION>_<OBJECT>` forms; the subsequent refinement dropped redundant `_TO` and
reserved `_FROM` for data-reversal.

**Dead-edge prune (pre-eviction, 2026-07-08).** The vocabulary previously declared
~23 edge types, but only the ones the collector actually emits (or the region seed
creates) carried any data. 15 defined-but-never-emitted edge types were deleted
rather than frozen into the release tag as speculative surface (an AI-legibility trap:
the schema implied aws_core modeled containment/attachment/protection when it modeled
none). Specific edges will be re-introduced — correctly named per the add-edge skill —
when a collector rule actually emits them. The generic `CONTAINS` edge (region→AZ seed)
was replaced by the specific `DIVIDED_INTO_AZ` (region → az, parent→child).

The categories (representative; the manifest is the canonical, enforced list):

| Category | Edge Types | Description |
| --- | --- | --- |
| Structural | DIVIDED_INTO_AZ | Region → availability zone reference topology (parent→child) |
| Operational | INVOKES, ROUTES_TRAFFIC, WRITES_LOGS, RETRIEVES_CONTENT_FROM, RETRIEVES_CERT_FROM | Runtime actions, traffic, and data retrieval (`_FROM` = data-backwards) |
| Access/Security | ASSUMES_ROLE, FEDERATES_INTO | IAM role assumption and federated identity |

Edge types use explicit `sources` and `targets` constraints where the relationship is well-defined (e.g. `ASSUMES_ROLE` from IAM users/roles, Lambda functions, and EventBridge rules to IAM roles; `RETRIEVES_CONTENT_FROM` from CloudFront distributions to S3 buckets). Where one end is genuinely open, only the other is constrained (e.g. `INVOKES` fixes its target to `aws_lambda` and leaves the source open).

Several edge types declare `property_schema` for structured edge metadata (e.g. `ROUTES_TRAFFIC` has optional `destination_cidr` and `port`; `INVOKES` has an optional `method`).

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-aws-core-edges-1 | Manifest-Canonical Inventory | Implemented | Edge types are declared in `tap-plugin.toml` and enforced by `validate_plugin` (every declared edge loads; `create_edge` succeeds for constrained types). The spec documents categories + convention, not a frozen count. | Replaces the prior "N edge types" census — derived state that drifted on every add. |
| req-aws-core-edges-2 | Constrained Where Appropriate | Implemented | Edge types with well-defined relationships use explicit source/target constraints. | |
| req-aws-core-edges-3 | Property Schemas | Implemented | Edge types that carry structured metadata declare property_schema. | |
| req-aws-core-edges-4 | Naming Convention | Implemented | Edge slugs follow the convention canonical in `tap_grid/skills/add-edge/SKILL.md` (mechanical; `<ACTION>_<OBJECT>`; action-direction; `_TO` never; `_FROM` = data-backwards; locative carve-out). | |

#### Open Questions

**Generic vs. specific edge types (resolved toward specific).** The vocabulary
formerly carried broad generic edges (`ATTACHED_TO`, `DEPENDS_ON`, `CONTAINS`,
`RESIDES_IN`, `PROTECTS`) meant to be reusable across resource types. In practice none
of them were ever emitted, and a generic edge conflates unrelated relationships (one
`ATTACHED_TO` bundled EBS↔EC2, policy↔role, EIP↔instance). The pre-eviction prune
resolved the trade-off toward **specific**: delete the unused generics, and add a
precise `<ACTION>_<OBJECT>` edge (per the add-edge skill) when a collector actually
emits that relationship. Generalized "what is inside what" is deferred to reified paths
over specific edges (`docs/misc/grid-native-paths-notes.md`), not a generic containment edge.

#### Future

CloudWatch logging (`WRITES_LOGS`) and the CloudFront retrieval edges landed with the boto3 collector demo set. Additional edge types will emerge for cross-account trust, VPC peering, and Transit Gateway connectivity. The deferred policy-document edge resolver (`spec-aws-core-collector-v0.md` req-aws-collector-nongoals) will add IAM/resource-policy-derived access edges as a post-ingestion pass.

### Reference Data
----
RID: `req-aws-core-reference`
Status: `Implemented`

Regions and availability zones are seeded as GRIFT data with `DIVIDED_INTO_AZ` edges
(region → az, parent→child; formerly the generic `CONTAINS`, replaced in the
pre-eviction edge prune).

#### Implementation

The `grift/regions.grift.json` file contains:

- 34 commercial AWS regions with region code, display name, and geographic area
- 108 availability zones with zone name and zone ID
- 108 DIVIDED_INTO_AZ edges linking each region to its AZs

Entity IDs use deterministic UUID ranges so that repeated GRIFT imports (upsert mode) update existing entities rather than creating duplicates:

- Regions: `01965b00-1000-7000-8000-*`
- AZs: `01965b00-2000-7000-8000-*`
- Edges: `01965b00-3000-7000-8000-*`

Data source: AWS official documentation at `docs.aws.amazon.com/global-infrastructure/latest/regions/`.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-aws-core-reference-1 | Commercial Regions Complete | Implemented | All standard commercial AWS regions are represented. | |
| req-aws-core-reference-2 | AZs Per Region | Implemented | All availability zones per region are represented with zone IDs. | |
| req-aws-core-reference-3 | DIVIDED_INTO_AZ Edges | Implemented | Every AZ has a DIVIDED_INTO_AZ edge from its parent region (region → az). | |
| req-aws-core-reference-4 | Deterministic IDs | Implemented | Entity IDs are deterministic for GRIFT upsert compatibility. | |
| req-aws-core-reference-5 | Schema Validated | Implemented | GRIFT file validates against `tap_grid/schemas/grift-document.schema.json`. | |

#### Future

Add Local Zones and Wavelength Zones when they become relevant for the compliance/operations use cases.

### Icon Assets
----
RID: `req-aws-core-icons`
Status: `Implemented`

Every model type has a corresponding SVG icon per the TAP grid icon specification.

#### Implementation

32 unique SVG icons live at `static/aws_core/icons/`. Icon keys use kebab-case (e.g. `aws-ec2`, `aws-vpc`). Several models share icon keys where the AWS service is the same:

- `aws-ecs` — EcsCluster, EcsService, EcsTask
- `aws-iam` — IamUser, IamRole, IamPolicy
- `aws-vpc` — Vpc, Subnet

Icons follow the TAP icon contract: 24x24 viewBox, `currentColor` fill, `aria-hidden="true"`, SVG format only. The plugin validation system's `loads` level verifies that every declared `ENTITY_ICON` resolves to an existing SVG file.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-aws-core-icons-1 | All Models Have Icons | Implemented | Every model declares ENTITY_ICON and the corresponding SVG exists. | |
| req-aws-core-icons-2 | TAP Icon Contract | Implemented | Icons follow the TAP grid icon specification (kebab-case, SVG, currentColor). | |
| req-aws-core-icons-3 | Validation Enforced | Implemented | Plugin validation at loads level checks icon key format and file existence. | |

#### Future

Replace placeholder icons with proper AWS Architecture Icons simplified to TAP's 24x24 single-color convention. The catalog refresh skill should handle icon updates.

### Computing Core Alignment
----
RID: `req-aws-core-computing-core`
Status: `Proposed`

Future alignment between AWS-native resource types and generic computing primitives is the responsibility of `aws_core`, not `computing_core`.

#### Implementation

`computing_core` defines the lower generic substrate. When TAP is ready to model cross-plugin relationships and dependencies, `aws_core` should adapt its provider-native resources to those generic primitives rather than requiring `computing_core` to carry AWS-specific accommodation logic.

Examples of future alignment work in `aws_core` may include:

- relating `aws_elastic_ip` to generic `ip_address`
- relating `aws_subnet` to generic `ip_subnet`
- relating `aws_ebs_volume` to generic `storage_volume` or `filesystem`
- relating AWS compute and container resources to `virtual_machine` or `container`
- introducing hotlink-backed synchronization where provider-native fields embed generic identifiers and TAP benefits from enforcing that contract

This specification does not yet define the exact cross-plugin edge family, hotlink contracts, dependency semantics, or load ordering rules. Those belong to a later phase once `computing_core` is stable and TAP is ready for plugin dependency design.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-aws-core-computing-core-1 | AWS Adapts Downward | Proposed | Future AWS-to-generic mapping is defined in `aws_core` rather than in `computing_core`. | |
| req-aws-core-computing-core-2 | Generic Substrate Respected | Proposed | `aws_core` treats `computing_core` as the lower generic substrate for relevant concepts. | |

#### Open Questions

Should `aws_elastic_ip.public_ip` eventually participate in a hotlink contract to a generic `ip_address` node across a future provider-to-generic edge such as `PROVIDES`, or should AWS/generic correspondence stay as ordinary graph relationships only? This is intentionally left open so TAP can decide later whether the embedded AWS field plus materialized generic node relationship is strong enough to justify hotlink synchronization.

### Plugin Validation
----
RID: `req-aws-core-validation`
Status: `Implemented`

The plugin passes TAP's centralized plugin validation system at all three levels.

#### Implementation

- **structure** — manifest, paths, edge files, directories, undeclared files
- **loads** — class imports, ENTITY_TYPE matching, icon validation
- **runs** — create_node for all 37 models, create_edge for constrained edge types, GRIFT import

Plugin-specific tests cover only domain behavior (field defaults, configuration round-trips). All structural, load, and runtime smoke testing is delegated to the centralized validator.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-aws-core-validation-1 | Structure Level Passes | Implemented | Plugin passes `validate_plugin --level structure`. | |
| req-aws-core-validation-2 | Loads Level Passes | Implemented | Plugin passes `validate_plugin --level loads`. | |
| req-aws-core-validation-3 | Runs Level Passes | Implemented | Plugin passes `validate_plugin --level runs`. | |

### v0 Non-Goals
----
RID: `req-aws-core-nongoals`
Status: `Proposed`

The following are explicitly deferred from v0:

- live AWS account discovery (querying a running account to populate the grid)
- AWS service catalog modeling (products vs. resource types)
- cross-account and cross-region edge inference
- CloudFormation/Terraform state import
- cost and billing data
- CloudWatch metrics and alarm integration
- Local Zones and Wavelength Zones
- GovCloud and China partition support
- plugin dependency declarations
- API endpoints for AWS-specific queries

#### Future

Live account discovery is the next major capability. It will require AWS credentials (assumed role or org-level access) and should populate all resource types, edges, and configuration metadata for a running AWS environment. The catalog refresh skill provides the foundation for this by maintaining the reference data that live discovery will build on.
