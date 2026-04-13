/**
 * tap_viz runtime: dynamic loader for tap layout modules.
 *
 * A tap layout is a JS file exporting `async function execute(context)`.
 * Layouts live at paths like `plugins/<plugin>/static/<plugin>/js/projections/foo.js`;
 * the projection definition stores this path in each elevation's `tap_layouts[i].js_file`.
 *
 * We resolve that path to a URL under /static/ and use native ES dynamic
 * import so layouts can themselves `import` runtime modules directly.
 */

const moduleCache = new Map();

/**
 * Convert a spec-form js_file path to a /static/-served URL.
 *
 * Accepted inputs:
 *   - "plugins/lotr/static/lotr/js/projections/saga.js"   (plugin static path)
 *   - "tap_viz/static/tap_viz/js/projections/foo.js"      (tap_viz static path)
 *   - "/static/lotr/js/projections/saga.js"               (already-resolved)
 */
export function resolveLayoutUrl(jsFile) {
    if (!jsFile) throw new Error("resolveLayoutUrl: jsFile required");
    if (jsFile.startsWith("/")) return jsFile;

    // Match "<anything>/static/<app>/..." and drop everything before /static/.
    const m = jsFile.match(/\/static\/(.+)$/);
    if (m) return `/static/${m[1]}`;

    // Fall back to treating the path as literal under /static/.
    return `/static/${jsFile}`;
}

/**
 * Dynamically import a tap layout module. Caches by resolved URL.
 *
 * @param {string} jsFile Layout path from the projection definition.
 * @returns {Promise<{execute: Function}>}
 */
export async function loadLayoutModule(jsFile) {
    const url = resolveLayoutUrl(jsFile);
    if (moduleCache.has(url)) return moduleCache.get(url);

    const promise = import(url).then((mod) => {
        if (typeof mod.execute !== "function") {
            throw new Error(`Layout module ${url} does not export execute()`);
        }
        return mod;
    });
    moduleCache.set(url, promise);
    return promise;
}

export function clearLayoutCache() {
    moduleCache.clear();
}
