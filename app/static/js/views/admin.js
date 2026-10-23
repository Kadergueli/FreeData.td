/**
 * View: Administration. Sign-in, strategic overview with alerts, audit journal.
 * Every dynamic value is escaped; nothing here is reachable without a valid admin session
 * (the server enforces it — this page only reflects it).
 */

import { loadConfig, signIn, signOut, getSession, adminFetch } from '../admin_client.js';
import { showToast, formatDate } from '../ui.js';
import { t } from '../i18n.js';
import { escapeHtml } from '../sanitize.js';

const SECTOR_IDS = ['agriculture', 'environment', 'markets', 'transport', 'education', 'economy', 'health', 'energy'];
let _tab = 'overview';
let _me = null;

const root = () => document.getElementById('admin-root');
const sectorName = (id) => { const k = `sectors.names.${id}`; const v = t(k); return v === k ? id : v; };

function fmtDateTime(raw) {
  if (!raw) return '—';
  const d = new Date(raw);
  if (isNaN(d.getTime())) return escapeHtml(String(raw));
  return `${formatDate(raw)} ${d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })}`;
}

function daysAgo(raw) {
  if (!raw) return null;
  const d = new Date(raw);
  if (isNaN(d.getTime())) return null;
  return Math.max(0, Math.floor((Date.now() - d.getTime()) / 86400000));
}

function alertText(a) {
  const key = `admin.alerts.${a.code}`;
  let txt = t(key);
  if (txt === key) return a.message;                       // unknown code: server's English text
  Object.entries(a.params || {}).forEach(([k, v]) => {
    txt = txt.replace(`{${k}}`, k === 'sector' ? sectorName(v) : String(v));
  });
  return txt;
}

/* ── Sign-in ─────────────────────────────────────────────────────────────── */

function renderLogin(message = '') {
  root().innerHTML = `
    <div class="card" style="max-width:420px;margin:32px auto;padding:24px;">
      <div class="mono-xs text-cyan fw-700 mb-1 flex items-center gap-1 uppercase">
        <i data-lucide="shield" style="width:14px;height:14px;"></i> ${t('admin.restricted')}
      </div>
      <h2 class="mono-lg fw-700 mb-4">${t('admin.login_title')}</h2>
      ${message ? `<p class="mono-sm text-accent mb-3" id="admin-login-error" role="alert">${escapeHtml(message)}</p>` : ''}
      <form id="admin-login-form" class="flex flex-col gap-3">
        <label class="mono-xs text-muted uppercase" for="admin-email">${t('admin.email')}</label>
        <input class="input-search" type="email" id="admin-email" autocomplete="username" required>
        <label class="mono-xs text-muted uppercase" for="admin-password">${t('admin.password')}</label>
        <input class="input-search" type="password" id="admin-password" autocomplete="current-password" required>
        <button class="btn btn-primary justify-center mono-md fw-700" type="submit" id="admin-login-btn" style="padding:12px;">
          ${t('admin.sign_in')}
        </button>
      </form>
    </div>`;
  if (window.lucide) window.lucide.createIcons();

  document.getElementById('admin-login-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const btn = document.getElementById('admin-login-btn');
    btn.disabled = true;
    try {
      const cfg = await loadConfig();
      await signIn(cfg, document.getElementById('admin-email').value.trim(), document.getElementById('admin-password').value);
      _me = await adminFetch('/session', { method: 'POST' });
      renderDashboard();
    } catch (err) {
      signOut();
      const msg = err.status === 403 ? t('admin.not_admin')
        : err.status === 400 ? t('admin.bad_credentials')
        : `${t('admin.login_failed')}: ${err.message}`;
      renderLogin(msg);
    }
  });
}

/* ── Dashboard shell ─────────────────────────────────────────────────────── */

function renderDashboard() {
  const tabs = [['overview', 'admin.tab_overview'], ['audit', 'admin.tab_audit']];
  root().innerHTML = `
    <div class="flex justify-between items-center flex-wrap gap-3 mb-4">
      <div>
        <div class="mono-xs text-cyan fw-700 mb-1 flex items-center gap-1 uppercase">
          <i data-lucide="shield-check" style="width:14px;height:14px;"></i> ${t('admin.restricted')}
        </div>
        <h2 class="hero-title uppercase" style="font-size:24px;">${t('admin.title')}</h2>
      </div>
      <div class="flex items-center gap-2">
        <span class="mono-xs text-muted" id="admin-who">${escapeHtml(_me.email)}</span>
        <span class="badge badge--cyan mono-xs">${escapeHtml(_me.role.toUpperCase())}</span>
        <button class="btn btn-ghost mono-xs" id="admin-signout" type="button">${t('admin.sign_out')}</button>
      </div>
    </div>
    <div class="flex gap-2 mb-4 flex-wrap" id="admin-tabs">
      ${tabs.map(([id, key]) => `<button type="button" class="btn ${id === _tab ? 'btn-cyan' : 'btn-ghost'} admin-tab mono-sm" data-tab="${id}" aria-pressed="${id === _tab}">${t(key)}</button>`).join('')}
    </div>
    <div id="admin-panel"></div>`;
  if (window.lucide) window.lucide.createIcons();

  document.getElementById('admin-signout').addEventListener('click', () => { signOut(); _me = null; renderLogin(); });
  document.querySelectorAll('.admin-tab').forEach(btn => btn.addEventListener('click', () => {
    _tab = btn.dataset.tab;
    document.querySelectorAll('.admin-tab').forEach(b => {
      const on = b === btn;
      b.classList.toggle('btn-cyan', on); b.classList.toggle('btn-ghost', !on);
      b.setAttribute('aria-pressed', String(on));
    });
    renderPanel();
  }));
  renderPanel();
}

function renderPanel() {
  const panel = document.getElementById('admin-panel');
  if (!panel) return;
  panel.innerHTML = `<p class="mono-sm text-muted"><span class="skeleton" style="width:240px;"></span></p>`;
  (_tab === 'audit' ? loadAudit : loadOverview)(panel).catch(handlePanelError);
}

function handlePanelError(err) {
  if (err.status === 401 || err.status === 403) { signOut(); _me = null; renderLogin(t('admin.session_expired')); return; }
  const panel = document.getElementById('admin-panel');
  if (panel) panel.innerHTML = `<div class="card" style="padding:16px;border-color:var(--red);">
    <p class="mono-sm text-accent mb-2">${t('admin.load_failed')}: ${escapeHtml(err.message)}</p>
    <button class="btn btn-ghost mono-xs" id="admin-retry" type="button">${t('admin.retry')}</button></div>`;
  document.getElementById('admin-retry')?.addEventListener('click', renderPanel);
}

/* ── Overview ────────────────────────────────────────────────────────────── */

const LEVEL_STYLE = {
  critical: { color: 'var(--red)', icon: 'octagon-alert' },
  warning: { color: 'var(--amber)', icon: 'triangle-alert' },
  info: { color: 'var(--cyan)', icon: 'info' },
};

function sectorState(s) {
  if (s.count === 0) return ['empty', 'var(--red)'];
  if (s.count == null) return ['unknown', 'var(--text-muted)'];
  const d = daysAgo(s.last_published);
  if (d != null && d > 14) return ['late', 'var(--amber)'];
  return ['ok', 'var(--green)'];
}

async function loadOverview(panel) {
  const o = await adminFetch('/overview');
  const sch = (o.service && o.service.scheduler) || {};
  const q = o.quality || {};
  const score = typeof q.score_global === 'number' && Number(q.total_public) > 0 ? `${(q.score_global * 100).toFixed(1)}%` : '—';
  const banner = { ok: ['var(--green)', 'admin.health_ok'], warning: ['var(--amber)', 'admin.health_warning'], critical: ['var(--red)', 'admin.health_critical'] }[o.health] || ['var(--text-muted)', 'admin.health_ok'];

  panel.innerHTML = `
    <div class="card mb-4" id="admin-health-banner" data-health="${escapeHtml(o.health)}" style="padding:16px;border-left:4px solid ${banner[0]};">
      <div class="flex justify-between items-center flex-wrap gap-2">
        <h3 class="mono-md fw-700" style="color:${banner[0]};">${t(banner[1])}</h3>
        <button class="btn btn-ghost mono-xs" id="admin-refresh" type="button"><i data-lucide="refresh-cw" style="width:13px;height:13px;"></i> ${t('admin.refresh')}</button>
      </div>
      <div class="flex flex-col gap-2 mt-3" id="admin-alerts">
        ${o.alerts.length ? o.alerts.map(a => {
          const st = LEVEL_STYLE[a.level] || LEVEL_STYLE.info;
          return `<div class="flex items-start gap-2 admin-alert" data-level="${escapeHtml(a.level)}" data-code="${escapeHtml(a.code)}">
            <i data-lucide="${st.icon}" style="width:16px;height:16px;flex-shrink:0;color:${st.color};margin-top:2px;"></i>
            <span class="mono-sm">${escapeHtml(alertText(a))}</span></div>`;
        }).join('') : `<p class="mono-sm text-muted">${t('admin.no_alerts')}</p>`}
      </div>
    </div>

    <div class="grid-2 mb-4">
      <div class="card" style="padding:16px;"><h4 class="mono-xs text-muted uppercase mb-2">${t('home.stat_obs')}</h4>
        <div class="mono-2xl fw-700" id="admin-kpi-total">${o.data.total == null ? '—' : Number(o.data.total).toLocaleString()}</div>
        <div class="mono-xs text-muted mt-1">${t('admin.last_publication')}: ${fmtDateTime(o.data.last_update)}</div></div>
      <div class="card" style="padding:16px;"><h4 class="mono-xs text-muted uppercase mb-2">${t('home.stat_score')}</h4>
        <div class="mono-2xl fw-700" id="admin-kpi-score">${score}</div>
        <div class="mono-xs text-muted mt-1">${t('admin.anomalies')}: ${q.anomalies == null ? '—' : q.anomalies} · ${t('admin.regions')}: ${o.data.regions_covered}/23</div></div>
    </div>

    <div class="card mb-4" style="padding:16px;">
      <h4 class="mono-sm uppercase mb-3">${t('admin.sectors_title')}</h4>
      <div style="overflow-x:auto;"><table class="ds-table" id="admin-sectors">
        <thead><tr>
          <th class="mono-xs text-muted" style="text-align:left;padding:6px 10px;">${t('admin.th_sector')}</th>
          <th class="mono-xs text-muted" style="text-align:right;padding:6px 10px;">${t('admin.th_count')}</th>
          <th class="mono-xs text-muted" style="text-align:left;padding:6px 10px;">${t('admin.th_last')}</th>
          <th class="mono-xs text-muted" style="text-align:left;padding:6px 10px;">${t('admin.th_state')}</th></tr></thead>
        <tbody>${SECTOR_IDS.map(id => {
          const s = o.data.sectors.find(x => x.id === id) || { id, count: null, last_published: null };
          const [state, color] = sectorState(s);
          const d = daysAgo(s.last_published);
          return `<tr data-sector="${escapeHtml(id)}" data-state="${state}">
            <td class="mono-xs fw-600" style="padding:8px 10px;">${escapeHtml(sectorName(id))}</td>
            <td class="mono-xs" style="padding:8px 10px;text-align:right;">${s.count == null ? '—' : Number(s.count).toLocaleString()}</td>
            <td class="mono-xs text-muted" style="padding:8px 10px;">${s.last_published ? `${fmtDateTime(s.last_published)} (${d} ${t('admin.days_short')})` : '—'}</td>
            <td style="padding:8px 10px;"><span class="badge" style="color:${color};border-color:${color};background:transparent;">${t(`admin.state_${state}`)}</span></td></tr>`;
        }).join('')}</tbody></table></div>
    </div>

    <div class="card" style="padding:16px;">
      <h4 class="mono-sm uppercase mb-3">${t('status.sched_title')}</h4>
      <div class="grid-2">
        <div><div class="mono-xs text-muted uppercase mb-1">${t('status.sched_last')}</div><div class="mono-sm" id="admin-sched-last">${sch.last_run ? fmtDateTime(sch.last_run) : t('status.sched_never')}</div></div>
        <div><div class="mono-xs text-muted uppercase mb-1">${t('admin.storage')}</div><div class="mono-sm">${escapeHtml(String((o.service.storage_backend || '—')).toUpperCase())}</div></div>
      </div>
    </div>`;
  if (window.lucide) window.lucide.createIcons();
  document.getElementById('admin-refresh')?.addEventListener('click', renderPanel);
}

/* ── Audit journal ───────────────────────────────────────────────────────── */

async function loadAudit(panel) {
  const { entries } = await adminFetch('/audit-log?limit=100');
  panel.innerHTML = `<div class="card" style="padding:16px;">
    <h4 class="mono-sm uppercase mb-3">${t('admin.audit_title')}</h4>
    <p class="mono-xs text-muted mb-3">${t('admin.audit_desc')}</p>
    ${entries.length ? `<div style="overflow-x:auto;"><table class="ds-table" id="admin-audit-table"><thead><tr>
      <th class="mono-xs text-muted" style="text-align:left;padding:6px 10px;">${t('admin.th_when')}</th>
      <th class="mono-xs text-muted" style="text-align:left;padding:6px 10px;">${t('admin.th_who')}</th>
      <th class="mono-xs text-muted" style="text-align:left;padding:6px 10px;">${t('admin.th_action')}</th>
      <th class="mono-xs text-muted" style="text-align:left;padding:6px 10px;">${t('admin.th_target')}</th></tr></thead><tbody>
      ${entries.map(e => {
        const k = `admin.actions.${e.action}`; const label = t(k) === k ? e.action : t(k);
        return `<tr><td class="mono-xs" style="padding:8px 10px;white-space:nowrap;">${fmtDateTime(e.created_at)}</td>
          <td class="mono-xs" style="padding:8px 10px;">${escapeHtml(e.admin_email)}</td>
          <td class="mono-xs fw-600" style="padding:8px 10px;">${escapeHtml(label)}</td>
          <td class="mono-xs text-muted" style="padding:8px 10px;">${escapeHtml(e.target || '')}</td></tr>`;
      }).join('')}</tbody></table></div>` : `<p class="mono-sm text-muted">${t('admin.no_entries')}</p>`}
  </div>`;
}

/* ── View ────────────────────────────────────────────────────────────────── */

export const AdminView = {
  render() {
    _tab = 'overview';
    return `<div id="admin-root"><p class="mono-sm text-muted"><span class="skeleton" style="width:200px;"></span></p></div>`;
  },

  async init() {
    let cfg;
    try { cfg = await loadConfig(); } catch (err) {
      root().innerHTML = `<p class="mono-sm text-accent">${t('admin.load_failed')}: ${escapeHtml(err.message)}</p>`;
      return;
    }
    if (!cfg.enabled) {
      root().innerHTML = `<div class="card" style="padding:20px;"><p class="mono-sm text-muted" id="admin-disabled">${t('admin.not_configured')}</p></div>`;
      return;
    }
    if (getSession()) {
      try { _me = await adminFetch('/me'); renderDashboard(); return; } catch (err) { signOut(); if (err.status === 403) { renderLogin(t('admin.not_admin')); return; } }
    }
    renderLogin();
  },
};
