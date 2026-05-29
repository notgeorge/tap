/**
 * format.js — Shared display-formatting helpers for TAP Viz.
 *
 * Pure, presentation-only string formatting. These helpers never carry the
 * canonical value: callers store the exact datum (e.g. a true integer count)
 * on the element and use these only to derive the human-facing label, so the
 * abbreviation is always a lossy *view*, never the source of truth.
 */

const UNITS = [
    ["k", 1e3],
    ["M", 1e6],
    ["B", 1e9],
];

/**
 * Abbreviate a count into a compact, visually-stable label.
 *
 * Rules (chosen so the rendered width stays bounded — see spec-viz-stack.md
 * req-viz-stack-count-format):
 *   - < 1000          → exact integer        ("1", "42", "999")
 *   - >= 1000         → scaled to k / M / B
 *       - mantissa < 10 → one decimal, trailing ".0" dropped  ("1.2k", "9.9k", "2k")
 *       - mantissa >= 10 → integer                            ("12k", "120k", "15M")
 *   - rounding is half-up; a carry that pushes the mantissa to >= 1000
 *     rolls up to the next unit ("999,999" → "1M", not "1000k")
 *
 * Non-finite / null input returns "" so a caller can treat "no value" as
 * "no chip". Negative inputs keep a leading "-".
 *
 * @param {number} n
 * @returns {string}
 */
export function humanizeCount(n) {
    if (n == null || !Number.isFinite(n)) return "";
    const sign = n < 0 ? "-" : "";
    const v = Math.abs(n);

    if (v < 1000) return sign + String(Math.round(v));

    // Largest unit whose threshold v clears; the carry branch can bump this up.
    let idx = 0;
    for (let i = 0; i < UNITS.length; i++) {
        if (v >= UNITS[i][1]) idx = i;
    }

    for (;;) {
        const [suffix, divisor] = UNITS[idx];
        const scaled = v / divisor;

        if (scaled < 10) {
            const rounded = Math.round(scaled * 10) / 10;
            // 9.96 → 10.0: read as an integer at this unit rather than "10.0".
            if (rounded >= 10) return sign + String(Math.round(scaled)) + suffix;
            const text = rounded % 1 === 0 ? String(rounded) : rounded.toFixed(1);
            return sign + text + suffix;
        }

        const rounded = Math.round(scaled);
        // 999.999k rounds to 1000k → roll up to the next unit if one exists.
        if (rounded >= 1000 && idx < UNITS.length - 1) {
            idx += 1;
            continue;
        }
        return sign + String(rounded) + suffix;
    }
}

/**
 * Exact, grouped rendering of an integer for tooltips / disclosure surfaces
 * where the precise value matters ("1,234"). Reads the stored datum directly;
 * never re-expands a humanized string.
 *
 * @param {number} n
 * @returns {string}
 */
export function exactCount(n) {
    if (n == null || !Number.isFinite(n)) return "";
    return Math.round(n).toLocaleString("en-US");
}
