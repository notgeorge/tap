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


# Crazy Talk

Timeshifting - can pull a copy of a graph into a new instance and roll back the clock to push all nodes to a set time, then play forward (just...wow.), or implement as a UI / layout function, rolling backwards and forwards in time.  Search across time is also going to have to be a thing.


# Done!

X Edge restrictions for node connections, node-specific limits prevents plugins from extending.  That said it may be best of both worlds to have both, which would result in complex tabulations up front, but the maximum breadth of use case scenarios.