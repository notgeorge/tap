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
    extend: {},
  },
  plugins: [],
}
