/**
 * Escapes a string for safe insertion into HTML via innerHTML/template literals.
 * Use this on ANY dynamic value (API data, LLM output, user input) before
 * interpolating it into an innerHTML template — never insert raw values.
 *
 * @param {*} value - value to escape (coerced to string; null/undefined -> '')
 * @returns {string} HTML-safe string
 */
export function escapeHtml(value) {
  if (value === null || value === undefined) return '';
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}
