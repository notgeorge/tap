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




