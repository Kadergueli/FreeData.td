/**
 * Admin session + API calls.
 * Sign-in is done directly against Supabase Auth (e-mail + password): the FreeData server
 * never receives the password, only the resulting access token (Authorization: Bearer).
 * The session lives in sessionStorage (cleared when the tab closes) and is refreshed
 * transparently when the access token expires.
 */

const KEY = 'fd_admin_session';
let _config = null;

export function getSession() {
  try { return JSON.parse(sessionStorage.getItem(KEY) || 'null'); } catch (_) { return null; }
}
function saveSession(s) { try { sessionStorage.setItem(KEY, JSON.stringify(s)); } catch (_) { /* private mode */ } }
export function clearSession() { try { sessionStorage.removeItem(KEY); } catch (_) { /* ignore */ } }

export async function loadConfig() {
  if (_config) return _config;
  const res = await fetch('/api/v1/config');
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  _config = (await res.json()).admin || { enabled: false };
  return _config;
}

async function authCall(cfg, path, body) {
  const res = await fetch(`${cfg.supabase_url}/auth/v1/${path}`, {
    method: 'POST',
    headers: { apikey: cfg.anon_key, 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  let data = {};
  try { data = await res.json(); } catch (_) { /* empty */ }
  if (!res.ok) {
    const err = new Error(data.error_description || data.msg || data.message || `HTTP ${res.status}`);
    err.status = res.status;
    throw err;
  }
  return data;
}

function toSession(data) {
  return {
    access_token: data.access_token,
    refresh_token: data.refresh_token,
    expires_at: Date.now() + (Number(data.expires_in) || 3600) * 1000,
    email: data.user && data.user.email,
  };
}

export async function signIn(cfg, email, password) {
  const data = await authCall(cfg, 'token?grant_type=password', { email, password });
  const s = toSession(data);
  saveSession(s);
  return s;
}

async function refreshSession(cfg) {
  const cur = getSession();
  if (!cur || !cur.refresh_token) throw new Error('No session');
  const data = await authCall(cfg, 'token?grant_type=refresh_token', { refresh_token: cur.refresh_token });
  const s = toSession(data);
  s.email = s.email || cur.email;
  saveSession(s);
  return s;
}

export function signOut() { clearSession(); }

/** Call an /api/v1/admin/* endpoint. Retries once after a token refresh on 401.
 *  Throws Error with .status (401 = not signed in, 403 = not an administrator). */
export async function adminFetch(path, { method = 'GET', body } = {}) {
  const cfg = await loadConfig();
  let session = getSession();
  if (!session) { const e = new Error('Not signed in'); e.status = 401; throw e; }
  if (session.expires_at - Date.now() < 30000) {
    try { session = await refreshSession(cfg); } catch (_) { clearSession(); const e = new Error('Session expired'); e.status = 401; throw e; }
  }
  const call = (tok) => fetch(`/api/v1/admin${path}`, {
    method,
    headers: { Authorization: `Bearer ${tok}`, ...(body ? { 'Content-Type': 'application/json' } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  });
  let res = await call(session.access_token);
  if (res.status === 401) {
    try { session = await refreshSession(cfg); res = await call(session.access_token); } catch (_) { /* fall through */ }
  }
  if (!res.ok) {
    let detail = '';
    try { detail = (await res.json()).detail; } catch (_) { /* not JSON */ }
    const err = new Error(typeof detail === 'string' && detail ? detail : `HTTP ${res.status}`);
    err.status = res.status;
    if (res.status === 401) clearSession();
    throw err;
  }
  return res.json();
}
