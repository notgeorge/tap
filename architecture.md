You are a senior software architect working with a single developer of moderate experience who has world-class architectural experience and instincts.

You will scaffold a Python/Django-based system strictly according to the following architecture.md.

Rules:
- Do not invent concepts not present in the document.
- Treat Entity as the authoritative system of record similar to wikibase / wikidata
- Do not introduce multi-tenancy.
- Do not introduce autonomous agent actions.
- Start with the core data model first, then the plugin interfaces.
- Prefer clarity and inspectability over cleverness.

Generate code incrementally and explain design decisions briefly.

The Analagy Platform (TAP) is a general-purpose systems-mastery platform that blends humans, ai, and software that is being developed for immediate applications in security, compliance, and operations. 

Core Concepts
Entity: the atomic unit of meaning in TAP. All domain objects are entities. This is the authoritative symbol ground for meaning in TAP.  The django standard ORM data model tables and the edge table reference entity Id as a column / key. All entity IDs are UUIDv7.
Edge: a directed, typed relationship between two entities referencing the entity table
Realm: a scoped graph context representing a perspective of the same system (e.g. design, configuration, operation, stored as a column on all applicable tables). Edges are represented in the Entity table.
Environment:  Separation of scoped and branched versions of a graph for dev / stage / prod and more complex intermediate states ala dev-v1 dev-v2
System: a bounded collection of entities and edges representing something being managed (ala a cloud SAAS service)
Plugin: a module that introduces to TAP new entity types, edge types, constraints, and behaviors and which may depend on other plugins

The TAP platform is built in python using the django platform to provide initial scaffolding, authentication, and ORM with graph capabilities.  Configuration of TAP for a specific use case / domain / product will be performed through a robust plugin mechanism which introduce domain specific schemas, views, operations, and will eventually include capabilities beyond django / python such as containers.

Fundamental Design Choices / Key differentiatiors that distinguish TAP from exsiting CRM, compliance, systems-management tools and are critical for the success of the project.

1. Graph-capabilities in a standard SQL database - these will be implemented using an entity table spine and a dedicated edge table to support directed graphs across the domain.  This approach provides the strong type, security, ACID guarantees of SQL which most graph dbs lack, while still being able to implement the useful parts of graph models for traversals (potentially using recursive CTE calls on postgres). An essential capability will be data history to the point of field-level-information-provenance (FLIP) which will require a careful balance of both graph and sql concepts (this is not audit logs, this is per-data-item history / change-log).

2. Visualization - capabilites for humans to view and interact with the data in a graphical way, think google maps meets visio.  

3.  Realms and Environments - Leverage the graph structure to include multiple realms / perspectives of the system such as the design graph, configuration graph, operation graph (where the three should match to confirm system operation) and to enable multiple environments tracking the same concepts to be managed on the same system (ala  the contents of a SAAS dev / stage / prod deployments).

2. Plugin System - The plugin model avoids over-specifying the domains in which the platform can work, we're shooting to begin with implementing a set of first principles that apply to all systems (graph / traversal, history, schema management, security) which comprise the core of TAP, then use plugins to define the domain, interactions, and allow for highly customized features both within the django framework and outside of it while still allowing even outside components like containers and remote services to be managed (via plugin features) from within the TAP installation.  Plugins can also be scaffolded and have dependent plugins to further modularize / contain code and capabilites while still allowing use-case expansion.

3. LLM Integration bakes in the RAG-able capabilites throughout the application, data model, plugin system, and everywhere else that matters to enable first-class LLM agentic operation and support.  This separates it from existing applications and services which are manically trying to shoe-horn these capabilities in.  Agentic alignment is a first-class, built-in, ground-up priority with the ability to traverse graphs, summarize state, suggest actions and point out gaps but do not have control ability for now.

4. Federation - Eventually the application will support federation with other TAP / similar systems, making it possible to perform extended queries, import / export, synchronization.  The details of this will need to be worked out at a later time, but will inform some of the initial database core schemas to include things like where an entity originated from.


TAP Runtime Loop (Conceptual)
* Pre-requisite - TAP installed, necessary plugins added to define schemas and functionality, configured as necessary to meet the use case
* Ingest or discover facts about a system
* Normalize them into entities and edges
* Record provenance at field level
* Evaluate relationships and constraints
* Accept recommendations or actions
* Update the graph and provenance
* Present state to humans and LLMs via graph visualization, alerts, tables, dashboards


Critical, essential elements of TAP:
1.  Written in python and django with postgres and Django Ninja for customer-facing API (django admin api for django-standard admin operations) all bundled as a single container
2.  Extends the base django ORM to include Entity for symbol grounding and lightweight Edge table (from, to, type of connection) for graph functionality
3.  Uses cytoscape initially as the user-facing graphical view system
4.  Supports a data model where graphs can be isolated into different realms
5.  Uses plugins to isolate capabilities, plugins can import / depend on other plugins based initially on Simon Willison's django plugin approach
6.  Considers every place in the architecture where touch points and surfaces can be exposed to support LLM integration ala RAG
7.  Uses django's existing security model for authentication and best practices for data isolation
8.  Each installation is single-tenant, although parts of the graph can be isolated into "projects" with their own security roles for read / write
9.  All entity ids are based on UUIDv7
10. Data objects have their own icon which can be used in visualizations, graphs, tables
11. Can run on-prem with no connection to the Internet, all data and operations are 100% local to the application, no remote imports
12. Supports federation as a distant target


What TAP is definitely not
1.  A product created specifically for a specific system or use-case - it has core capabilities applicable to all systems, plugins implement domain-specificity
2.  Just another CRM, GRC, CMS based on standard CRUD / SQL concepts - graph and plugins enable exactly those use cases and many, many, more
3.  A toy product good for small projects and systems - it's built to scale to the largest systems humanity has ever created (and bigger).
4.  A shoe-horned together AI integration money play - built with AI as an accelerator from day one with full awareness of the tech's current strengths and weaknesses

Pithy blurbs:
* Wordpress / Salesforce / ServiceNow for managing systems
* Google Maps meets Visio meets Wikipedia
* Semantic web for humans instead of homo economicus
* Palantir for the people

Rampart is a TAP-managed system whose plugins create a domain for continuous compliance of SAAS services
The plugin set defines:
* infrastructure, control, signal entities
* dashboards for visualization and compliance monitoring
* continuously ingest information about the infrastructure to update the graph
* Uses FedRAMP 20x for initial control satisfaction, but is extensible to other security compliance regimes
* Rampart is explicitly read-only in the initial pass.  It presents a compliance scorecard for human users to perform remediation actions outside of Rampart but has sufficient context to suggest what to do via LLM integration.

Step-wise Priority Goals for v0
1. tap_core - Core data model - we define entity and edge tables connecting to standard ORM data tables and decide how to best structure where that standardized logic lives, including service-layer decisions that touch multiple tables
2. tap_plugins - plugin management - minimal implementation designed to seed data types for testing / implementation, this will grow and evolve, shooting bare minimum to add data objects, edges to prove core is working properly
3. tap_api - Manages API versioning, auth, and global API behavior, building out django ninja so there's an api layer that is minimal and effective and decide how to refactor plugins to support adding api endpoints in a sane way
4. tab_web - Assets and helpers for building expressive dashboards and UIs which plugins will extend, once this is baked we can refactor the plugin from built in step 2 to include some pages to see things
5. tap_viz - Visualization - present views of the data in visual graphical format (cytoscape), once we can see web pages we'll add cool visuals that will be a joyful thing to see
6. tap_flip - FLIP - to include data provenance, history tracking, realms, and environments, by this point we should know what we're doing and can knock out an initial version that is elegant and leverages the core model
7. tap_ai - Initial RAG / LLM Surfaces - read-only graph traversal, summarization, and suggestion helpers, the super-awesome stretch goal which takes this whole project to the next level

Once V0 is complete we'll move on to:
1.  Rampart plugin set
2.  Refinements for ease-of-use such as installation streamlining, user documentation
3.  First customer for Rampart to identify successes, pain points, and refactor
4.  Extend deployments to other Rampart customers to establish a financial base
5.  Expand to other domains


Explicit Non-Goals (v0)
* Agentic actions to modify the graph
* Multi-tenant SaaS
* Full OSCAL parity
* Cross-organization federation

What I have not formally defined until we get to that step in the implementation:
1. How FLIP is implemented to leverage the entity / edge table to capture all the necessary use cases for history and provenance


