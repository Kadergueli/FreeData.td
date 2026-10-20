/**
 * Small shared UI helpers (no dependencies).
 */

/** Non-blocking, screen-reader friendly replacement for alert().
 *  type: 'success' | 'error' | 'info'. Returns nothing. */
export function showToast(message, type = 'info', durationMs = 6000) {
  let host = document.getElementById('toast-host');
  if (!host) {
    host = document.createElement('div');
    host.id = 'toast-host';
    host.setAttribute('role', 'status');
    host.setAttribute('aria-live', 'polite');
    document.body.appendChild(host);
  }
  const el = document.createElement('div');
  el.className = `toast toast--${type}`;
  el.textContent = String(message); // textContent: never interpreted as HTML
  host.appendChild(el);
  const remove = () => el.remove();
  setTimeout(remove, durationMs);
  el.addEventListener('click', remove);
}

/** Format an ISO-ish date for display in the active locale; falls back to the raw text. */
export function formatDate(raw, locale) {
  if (!raw) return '';
  const d = new Date(raw);
  if (isNaN(d.getTime())) return String(raw);
  return d.toLocaleDateString(locale || undefined, { day: '2-digit', month: 'short', year: 'numeric' });
}
