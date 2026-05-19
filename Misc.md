# Misc Thoughts

## Batch
What is the BatchEvent table?

Really think through the implications of batch as an entity - i mean we'll want to sort, search, share it...

If storing types modified in the batch as some sort of json, be prepared for those types to disappear if plugins are removed.

How do we deal with federation and batching?  Inclined to keep batches on-host, but that breaks a sharing pattern.


## ToDo:

* graph column on basetable which lets us distinguish between enities related to data, history, page / web / layouts, search, and other stuff

* deletion approach once concensus is completed, this should be in core / grid and will require its own design doc.

* paths model - this should probably be a core feature along with search, perhaps an extension of baseModel since a path is a higher-level entity than a node and edge.  Perhaps it could be embedded in the edge metadata?

* testing strategy - need to operate from a base group of data / models so we aren't generating a bunch of models in each plugin


## Next Time

* Willison plugin system - register plugin, model, edges, ummmm other stuff, pages, apis, urls, panels?

* tap_web - alpine up front to support prettier stuff

* tap_grid instead of tap_grid, because all of this is the core of analogy

* extensible node types by appending extended_data to the database table, makes searchs more wonky, but that's what the search system is for.

* Clean module definitions, everything should be tight and self-contained, human readable to understand what's up (and need to add RAG handles)

* Pages and panels are nodes on the web graph.

* Search as a grid data model capability - include paths, traversals, canned searches, linked searches, the UI will be fun.

* Batch, history, and agreement page views (how do these ship - are they plugins that bring pages - do modules have plugins is that a thing?)


## Using Gen AI
* Need to actually review code edits at some point - lols maybe like RC2 or so - but i should be able to explain what's up

* Remember to actually read the plans and ask questions about things that you didn't include because duh.

* Seriously, avoid meta programming, it just gets ugl.


## Projects 

Reminded that projects set limts on which sections of graphs are viewable

In earlier designs they were inheritable - projects could import other projects

Could projects be used in place of environment (or are environments a sub-set of the project concept?)

Projects could be group-able by logical name or better to include a metadata object


## Skills

Brainstorming - scans the design files to support new strategizing about features, all in your head, no code, lovelace style.

Feature Development - use spec file format to implement a given feature, navigate spec files and code as needed (specs first, code later to save context)

Testing - specialized testing user to build out use cases exercing across modules and to hand off considerations that i think up (or find in the wild)

Plugin - builds out a plugin framework based on the currnet capabilities of the plugin system (idea, rate how good a plugin is at best practices)

Data Model - specifically for building nodes and edges, can consider other models that are being used in conjunction, will need a playground...


## Aliases (external canonical ids)

PURL / ARN / sha256 / URL are aliases, not competitors to entity_id.  Two layers, not a fork:

* entity_id (UUIDv7) = internal spine PK.  Opaque, coined, stable forever, uniform shape, great for graph perf + FLIP.  No external meaning.
* native_id (purl / arn / sha256 / url / dns_name / ...) = external canonical handle in the world's vocabulary for the thing.  What makes the entity joinable with external evidence (SBOMs, CVE feeds, other systems' inventories) and what makes re-ingest idempotent across collector runs.

Right design uses both.  `tap_grid/specs/spec-grid-aliases-BACKLOG.md` is the structural home: Entity.name stays canonical, aliases are typed kinds attached to the subject, named model is authoritative, contributor offers come via constrained graph paths.  Already designed.  Not built because nobody's paid for the use case yet.

Demand signal is here.  samsite-as-target made it concrete: 110 PURLs, 6 ARNs, 41 sha256s, 7 service URLs — every one an alias of a subject we'd ingest into the grid.  Federation between rampart and any other inventory needs join-by-native_id, not join-by-UUID.  Dedup on re-ingest needs the same.  FLIP per alias change is the point of having FLIP.

Stash native_id as a plugin attribute today; promote to first-class aliases when the use case has a buyer.

When the promotion happens: do **NOT** ship JSON-on-entity as the long-term home, even though that's what the spec's v1 says.  The spec is right to start there for cheap MVP, but the upgrade is:

* Uniqueness: postgres can't enforce UNIQUE(kind, value) inside a JSON array of objects across rows.  Federation lookup wants a real btree index, not a GIN-on-blob workaround.
* FLIP: per-alias history falls out naturally from a row.  JSON blob = coarse "aliases field changed" diffs, or you write structured array-diff handlers.  No thanks.
* Concurrent writers: two collectors landing aliases on the same subject = race on read-modify-write of the JSON, vs two INSERTs with ON CONFLICT on a table.
* Per-alias permissions / per-kind retention / dimension scoping: trivial on a row, gymnastic in JSON.

End-state: `EntityAlias(id, entity_id FK, kind, value, source_entity_id FK NULL, accepted_via, priority, primary_eligible, accepted_at)` as authoritative + a derived JSON projection on Entity for the display hot path (refreshed on alias change).  Table does constraints / FLIP / permissions; cache keeps display reads one-shot.  `ALIAS_POLICY` / `OFFERS_ALIAS` / handshake semantics from the spec are orthogonal to physical storage — unchanged.

Note: a normalized side-table is **not** the same as promoting aliases to first-class graph nodes.  The spec's "aliases are not graph nodes in v1" line stays correct.  Probably the right ceiling forever — aliases really are typed attributes of a subject, not subjects in their own right.

Honest scope: aliases solve identification + joinability.  They don't solve "is this PURL actually true of the bytes the entity represents" — that's the emitter-fidelity / attestation question and lives one layer up (Sigstore / Rekor / independent observation territory).  Don't conflate.


# Crazy Talk

Timeshifting - can pull a copy of a graph into a new instance and roll back the clock to push all nodes to a set time, then play forward (just...wow.), or implement as a UI / layout function, rolling backwards and forwards in time.  Search across time is also going to have to be a thing.


# Done!

X Edge restrictions for node connections, node-specific limits prevents plugins from extending.  That said it may be best of both worlds to have both, which would result in complex tabulations up front, but the maximum breadth of use case scenarios.