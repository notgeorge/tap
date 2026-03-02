# Page Spec


## Philosophy

Web interfaces are still very useful to have to present information to humans.  The page system in TAP will allow for users, plugin authors, and admins to generate pages to display information from the grid.  At a high level, a page is a container that makes space for one or more panels - specific views of the grid - and provides a set of features for coordinating the information shown in the panels such as shared page-level variables.

Pages tie into the web navigation system to present menus that users can click through to open a page and will be accessible to other navigation paradigms like AI / talk / cli as they are developed.

## Goals

1. Lightweight - pages don't contain logic beyond panel structure and page-level variables
2. Mobile Friendly - they should render properly on any type of screen, including mobile
3. 


## Requirements
### Page Objects
req-web-page-obj

A page object describes the layout of a web page based on having a:

* title:  Page title will be shown in browser tabs and in navigation links
* description:  what this is for, will be used when looking at pages but isn't necessarily printed on the page itself
* slug:  Path slug used in urls
* layout:  a columnar layout 

### Landing Pages
req-web-page-landing

### Navigation Bar
req-web-page-nav


## Specs