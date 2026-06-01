/** @type {import('tailwindcss').Config} */
module.exports = {
  // Static globs — resolved by the tailwindcss CLI directly, no Python plugin
  // discovery required (req-web-tailwind-pipeline-content-paths-2). Plugins
  // ship their own templates under plugins/*/templates and increasingly use
  // utility classes; without the third glob, classes used only in plugin
  // templates would silently miss the compiled CSS
  // (req-web-tailwind-pipeline-content-paths-1).
  content: [
    "./tap_web/templates/**/*.html",
    "./tap_viz/templates/**/*.html",
    "./plugins/**/templates/**/*.html",
  ],
  theme: {
    extend: {
      colors: {
        // Cool-neutral off-white page canvas — Tufte "paper, not glare". The
        // default app background (set on <html> in base.html); replaces cool
        // gray-50 / straight white. A faintly cool grey (B a hair above R/G)
        // rather than a warm cream, so it sits in the SAME family as TAP's cool
        // slate UI instead of clashing with it. Still lifts off pure white;
        // white panels/cards sit on it with subtle separation. Kept lighter
        // than slate-100 (#f1f5f9, used for hover/selected) so those still read.
        canvas: "#f4f5f7",
      },
    },
  },
  plugins: [],
}
