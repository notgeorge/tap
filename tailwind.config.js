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
        // Warm-neutral off-white page canvas — Tufte "paper, not glare". The
        // default app background (set on <html> in base.html); replaces cool
        // gray-50 / straight white. Deliberately warm-NEUTRAL (only a couple
        // points of warmth) rather than a saturated cream, so it lifts off
        // white without clashing with TAP's cool slate UI. White panels/cards
        // sit on it with subtle separation.
        canvas: "#f6f5f1",
      },
    },
  },
  plugins: [],
}
