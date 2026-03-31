You are a senior software architect working with a single developer of moderate experience who has world-class architectural experience and instincts.

You will scaffold a Python/Django-based system strictly according to the following architecture.md.

Rules:
- Do not invent concepts not present in the document.
- Treat the specifications as the canonical source of truth when this document is less precise or has drifted.
- Treat Entity as the canonical graph spine and higher-order metadata layer for TAP-managed nodes and edges.
- Do not introduce multi-tenancy.
- Do not introduce autonomous agent actions.
- Start with the core data model first, then the plugin interfaces.
- Prefer clarity and inspectability over cleverness.

Generate code incrementally and explain design decisions briefly.

The Analagy Platform (TAP) is a general-purpose systems-mastery platform that blends humans, ai, and software that is being developed for immediate applications in security, compliance, and operations. 

Core Concepts  
* Entity: the graph spine and canonical reference for TAP-managed nodes and edges. It holds cross-cutting metadata such as identity, dimensions, timestamps, and related higher-order capabilities. All entity IDs are UUIDv7.
* Edge: a directed, typed relationship between two entities. Edge is a first-class TAP object with its own table and a backing Entity on the spine.
* Dimensions: a flat JSON object stored on Entity used to scope, partition, and interpret TAP-managed graph objects.
* Service Layer: the canonical contract between applications and TAP-managed graph data. Node and edge reads/writes, batch-backed writes, discovery, constraints, and future security enforcement go through the service layer.
* System: a bounded collection of entities and edges representing something being managed (ala a cloud SAAS service)
* Plugin: a module that introduces to TAP new entity types, edge types, constraints, and behaviors and which may depend on other plugins
* Grid:  the totality of the data that is modeled on the sql-based graph implementation.

The TAP platform is built in python using the django platform to provide initial scaffolding, authentication, and ORM with graph capabilities.  Configuration of TAP for a specific use case / domain / product will be performed through a robust plugin mechanism which introduce domain specific schemas, views, operations, and will eventually include capabilities beyond django / python such as containers.

History, FLIP, and (in the near future) perspectives are core grid concepts of TAP rather than standalone product domains. They may have implementation modules, but architecturally they belong to the grid/service-layer model and should be treated as first-class graph capabilities rather than separate applications in their own right.

Fundamental Design Choices / Key differentiatiors that distinguish TAP from exsiting CRM, compliance, systems-management tools and are critical for the success of the project.

1. Graph-capabilities in a standard SQL database - these will be implemented using an entity table spine and a dedicated edge table to support directed graphs across the domain.  This approach provides the strong type, security, ACID guarantees of SQL which most graph dbs lack, while still being able to implement the useful parts of graph models for traversals (potentially using recursive CTE calls on postgres). An essential capability will be data history to the point of field-level-information-provenance (FLIP) which will require a careful balance of both graph and sql concepts (this is not audit logs, this is per-data-item history / change-log).

2. Visualization - capabilites for humans to view and interact with the data in a graphical way, think google maps meets visio.  

3.  Dimensions - Leverage dimensions on the Entity spine to include multiple graph contexts, namespaces, and perspectives without fragmenting the underlying node / edge model. Other scoping concepts such as realms, environments, and pocket dimensions may be explored later, but dimensions are the current implemented model.

2. Plugin System - The plugin model avoids over-specifying the domains in which the platform can work, we're shooting to begin with implementing a set of first principles that apply to all systems (graph / traversal, history, schema management, security) which comprise the core of TAP, then use plugins to define the domain, interactions, and allow for highly customized features both within the django framework and outside of it while still allowing even outside components like containers and remote services to be managed (via plugin features) from within the TAP installation.  Plugins can also be scaffolded and have dependent plugins to further modularize / contain code and capabilites while still allowing use-case expansion.

3. LLM Integration bakes in the RAG-able capabilites throughout the application, data model, plugin system, and everywhere else that matters to enable first-class LLM agentic operation and support.  This separates it from existing applications and services which are manically trying to shoe-horn these capabilities in.  Agentic alignment is a first-class, built-in, ground-up priority with the ability to traverse graphs, summarize state, suggest actions and point out gaps but do not have control ability for now.

4. Federation - Eventually the application will support federation with other TAP / similar systems, making it possible to perform extended queries, import / export, synchronization.  The details of this will need to be worked out at a later time, but will inform some of the initial database core schemas to include things like where an entity originated from.


TAP Runtime Loop (Conceptual)
* Pre-requisite - TAP installed, necessary plugins added to define schemas and functionality, configured as necessary to meet the use case
* Ingest or discover facts about a system
* Normalize them into entities and edges
* Route node and edge reads / writes through the service layer
* Record provenance at field level
* Evaluate relationships and constraints
* Accept recommendations or actions
* Update the graph and provenance
* Present state to humans and LLMs via graph visualization, alerts, tables, dashboards


Critical, essential elements of TAP:
1.  Written in python and django with postgres and Django Ninja for customer-facing API (django admin api for django-standard admin operations) all bundled as a single container
2.  Extends the base django ORM to include Entity as the graph spine, typed BaseModel tables for domain data, and a dedicated Edge table with backing Entity rows for graph functionality
3.  Uses cytoscape initially as the user-facing graphical view system
4.  Supports a data model where graph objects can be scoped and partitioned using dimensions on the Entity spine
5.  Uses plugins to isolate capabilities, plugins can import / depend on other plugins based initially on Simon Willison's django plugin approach
6.  Considers every place in the architecture where touch points and surfaces can be exposed to support LLM integration ala RAG
7.  Uses django's existing security model for authentication and best practices for data isolation
8.  Each installation is single-tenant, although dimensions and future security policy may be used to scope access to parts of the graph
9.  All entity ids are based on UUIDv7
10. Data objects have their own icon which can be used in visualizations, graphs, tables
11. Can run on-prem with no connection to the Internet, all data and operations are 100% local to the application, no remote imports
12. Supports federation as a distant target
13. Node and edge operations are expected to go through the TAP service layer rather than direct ORM access
14. TAP-managed types should be discoverable through registry-backed service-layer discovery rather than only through Python imports


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
* From Knowledge Graph to Wisdow Map

Rampart is a TAP-managed system whose plugins create a domain for continuous compliance of SAAS services
The plugin set defines:
* infrastructure, control, signal entities
* dashboards for visualization and compliance monitoring
* continuously ingest information about the infrastructure to update the graph
* Uses FedRAMP 20x for initial control satisfaction, but is extensible to other security compliance regimes
* Rampart is explicitly read-only in the initial pass.  It presents a compliance scorecard for human users to perform remediation actions outside of Rampart but has sufficient context to suggest what to do via LLM integration.

Step-wise Priority Goals for v0
1. tap_grid - Core data model - we define entity and edge tables connecting to standard ORM data tables and decide how to best structure where that standardized logic lives, including service-layer decisions that touch multiple tables
2. tap_plugins - plugin management - minimal implementation designed to seed data types for testing / implementation, this will grow and evolve, shooting bare minimum to add data objects, edges to prove core is working properly
3. tap_api - Manages API versioning, auth, and global API behavior, building out django ninja so there's an api layer that is minimal and effective and decide how to refactor plugins to support adding api endpoints in a sane way
4. tab_web - Assets and helpers for building expressive dashboards and UIs which plugins will extend, once this is baked we can refactor the plugin from built in step 2 to include some pages to see things
5. tap_viz - Visualization - present views of the data in visual graphical format (cytoscape), once we can see web pages we'll add cool visuals that will be a joyful thing to see
6. tap_ai - Initial RAG / LLM Surfaces - read-only graph traversal, summarization, and suggestion helpers, the super-awesome stretch goal which takes this whole project to the next level

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
1. How future scoping concepts beyond dimensions, such as pocket dimensions or perspectives, should be modeled
