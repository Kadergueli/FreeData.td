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

/** Validation score text for an /api/v1/pipeline/audit payload. Shown only when the
 *  platform actually measured one (rows exist AND the backend produced a score);
 *  otherwise "—" — never a made-up 100 %. */
export function formatScore(audit) {
  const s = audit && audit.reports_summary;
  if (!s || !(Number(s.total_public) > 0) || typeof s.score_global !== 'number') return '—';
  return `${(s.score_global * 100).toFixed(1)}%`;
}

/** Integer count or "—" when unknown (null/undefined). */
export function formatCount(n) {
  return typeof n === 'number' && isFinite(n) ? n.toLocaleString() : '—';
}
