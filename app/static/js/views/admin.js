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
let _qStatus = 'pending';
let _dSector = '';
let _dQuery = '';
let _pollTimer = null;
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
  const tabs = [['overview', 'admin.tab_overview'], ['collections', 'admin.tab_collections'], ['quality', 'admin.tab_quality'], ['data', 'admin.tab_data'], ['reports', 'admin.tab_reports'], ['team', 'admin.tab_team'], ['audit', 'admin.tab_audit']];
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
    clearTimeout(_pollTimer);
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
  ({ audit: loadAudit, collections: loadCollections, quality: loadQuality, data: loadData, reports: loadReports, team: loadTeam }[_tab] || loadOverview)(panel).catch(handlePanelError);
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

/* ── Collections: history + manual runs ──────────────────────────────────── */

const RUN_STYLE = {
  running: 'var(--cyan)', completed: 'var(--green)', partial: 'var(--amber)',
  failed: 'var(--red)', interrupted: 'var(--red)', skipped: 'var(--text-muted)',
};

function runDetails(r) {
  const res = r.results || {};
  const lines = Object.entries(res).filter(([, v]) => v && (v.error || (v.errors && v.errors.length) || v.held > 0))
    .map(([sec, v]) => `${sectorName(sec)}: ${[v.error, ...(v.errors || []), v.held > 0 ? t('admin.run_held').replace('{n}', v.held) : null].filter(Boolean).join(' ; ')}`);
  return lines.length ? `<div class="mono-xs text-muted" style="margin-top:4px;max-width:520px;white-space:normal;">${lines.map(escapeHtml).join('<br>')}</div>` : '';
}

async function loadCollections(panel) {
  const c = await adminFetch('/collections?limit=30');
  const running = !!c.job_running;
  const cur = c.current_run;
  panel.innerHTML = `
    <div class="card mb-4" style="padding:16px;">
      <h4 class="mono-sm uppercase mb-2">${t('admin.run_title')}</h4>
      <p class="mono-xs text-muted mb-3">${t('admin.run_desc')}</p>
      <div class="flex gap-3 flex-wrap mb-3" id="admin-run-sectors">
        ${c.sector_ids.map(id => `<label class="mono-xs flex items-center gap-1" style="cursor:pointer;">
          <input type="checkbox" class="admin-run-sector" value="${escapeHtml(id)}" ${running ? 'disabled' : ''}> ${escapeHtml(sectorName(id))}</label>`).join('')}
      </div>
      <div class="flex gap-2 flex-wrap items-center">
        <button class="btn btn-cyan mono-sm" id="admin-run-selected" type="button" ${running ? 'disabled' : ''}>${t('admin.run_selected')}</button>
        <button class="btn btn-ghost mono-sm" id="admin-run-all" type="button" ${running ? 'disabled' : ''}>${t('admin.run_all')}</button>
        <button class="btn btn-ghost mono-xs" id="admin-coll-refresh" type="button"><i data-lucide="refresh-cw" style="width:13px;height:13px;"></i> ${t('admin.refresh')}</button>
        <span class="mono-xs" id="admin-run-state" style="color:var(--cyan);">${running ? `${t('admin.run_in_progress')}${cur && cur.sectors ? ` (${escapeHtml(cur.sectors.map(sectorName).join(', '))})` : ''}` : ''}</span>
      </div>
      <p class="mono-xs mt-2" id="admin-run-msg" role="status"></p>
    </div>
    <div class="card" style="padding:16px;">
      <h4 class="mono-sm uppercase mb-3">${t('admin.history_title')}</h4>
      ${c.runs.length ? `<div style="overflow-x:auto;"><table class="ds-table" id="admin-runs-table"><thead><tr>
        <th class="mono-xs text-muted" style="text-align:left;padding:6px 10px;">${t('admin.th_when')}</th>
        <th class="mono-xs text-muted" style="text-align:left;padding:6px 10px;">${t('admin.th_trigger')}</th>
        <th class="mono-xs text-muted" style="text-align:left;padding:6px 10px;">${t('admin.th_sectors')}</th>
        <th class="mono-xs text-muted" style="text-align:left;padding:6px 10px;">${t('admin.th_state')}</th>
        <th class="mono-xs text-muted" style="text-align:right;padding:6px 10px;">${t('admin.th_stored')}</th></tr></thead><tbody>
        ${c.runs.map(r => {
          const tk = `admin.triggers.${r.trigger}`; const trig = t(tk) === tk ? r.trigger : t(tk);
          const color = RUN_STYLE[r.status] || 'var(--text-muted)';
          const secs = Array.isArray(r.sectors) ? r.sectors : [];
          const secTxt = secs.length >= c.sector_ids.length ? t('admin.all_sectors') : secs.map(sectorName).join(', ');
          return `<tr data-run-status="${escapeHtml(r.status)}">
            <td class="mono-xs" style="padding:8px 10px;white-space:nowrap;">${fmtDateTime(r.started_at)}</td>
            <td class="mono-xs" style="padding:8px 10px;">${escapeHtml(trig)}${r.triggered_by ? `<div class="text-muted">${escapeHtml(r.triggered_by)}</div>` : ''}</td>
            <td class="mono-xs" style="padding:8px 10px;">${escapeHtml(secTxt)}${runDetails(r)}</td>
            <td style="padding:8px 10px;"><span class="badge" style="color:${color};border-color:${color};background:transparent;">${t(`admin.run_status.${r.status}`)}</span></td>
            <td class="mono-xs" style="padding:8px 10px;text-align:right;">${Number(r.total_stored || 0).toLocaleString()}</td></tr>`;
        }).join('')}</tbody></table></div>` : `<p class="mono-sm text-muted" id="admin-no-runs">${t('admin.no_runs')}</p>`}
    </div>`;
  if (window.lucide) window.lucide.createIcons();

  const msg = document.getElementById('admin-run-msg');
  const start = async (sectors) => {
    try {
      const r = await adminFetch('/collections/run', { method: 'POST', body: { sectors } });
      msg.textContent = r.status === 'started' ? t('admin.run_started') : t('admin.run_already');
    } catch (err) {
      if (err.status === 401 || err.status === 403) { handlePanelError(err); return; }
      msg.textContent = `${t('admin.load_failed')}: ${err.message}`;
      return;
    }
    renderPanel();
  };
  document.getElementById('admin-run-all')?.addEventListener('click', () => start(null));
  document.getElementById('admin-run-selected')?.addEventListener('click', () => {
    const picked = [...document.querySelectorAll('.admin-run-sector:checked')].map(i => i.value);
    if (!picked.length) { msg.textContent = t('admin.run_pick'); return; }
    start(picked);
  });
  document.getElementById('admin-coll-refresh')?.addEventListener('click', renderPanel);

  // While a harvest runs, refresh the history every few seconds until it ends.
  clearTimeout(_pollTimer);
  if (running) {
    _pollTimer = setTimeout(() => { if (_tab === 'collections' && document.getElementById('admin-panel')) renderPanel(); }, 4000);
  }
}

/* ── Quality: quarantine review ──────────────────────────────────────────── */

function flagLabel(f) { const k = `admin.q_flags.${f}`; return t(k) === k ? f : t(k); }

function fmtNum(v) { return typeof v === 'number' ? String(Number(v.toPrecision(10))) : '—'; }

async function loadQuality(panel) {
  const q = await adminFetch(`/quarantine?status=${encodeURIComponent(_qStatus)}&limit=200`);
  const items = q.items || [];
  const statuses = ['pending', 'approved', 'corrected', 'rejected', 'all'];
  panel.innerHTML = `<div class="card" style="padding:16px;">
    <h4 class="mono-sm uppercase mb-2">${t('admin.q_title')}</h4>
    <p class="mono-xs text-muted mb-3">${t('admin.q_desc')}</p>
    <div class="flex gap-2 flex-wrap mb-3" id="admin-q-filters">
      ${statuses.map(st => `<button type="button" class="btn ${st === _qStatus ? 'btn-cyan' : 'btn-ghost'} mono-xs admin-q-filter" data-status="${st}" aria-pressed="${st === _qStatus}">
        ${t(`admin.q_status.${st}`)}${st !== 'all' && q.counts ? ` (${Number(q.counts[st] || 0)})` : ''}</button>`).join('')}
    </div>
    <p class="mono-xs mb-2" id="admin-q-msg" role="status"></p>
    ${items.length ? `<div style="overflow-x:auto;"><table class="ds-table" id="admin-q-table"><thead><tr>
      <th class="mono-xs text-muted" style="text-align:left;padding:6px 10px;">${t('admin.q_th_obs')}</th>
      <th class="mono-xs text-muted" style="text-align:right;padding:6px 10px;">${t('admin.q_th_value')}</th>
      <th class="mono-xs text-muted" style="text-align:left;padding:6px 10px;">${t('admin.q_th_flags')}</th>
      <th class="mono-xs text-muted" style="text-align:left;padding:6px 10px;">${t('admin.q_th_review')}</th></tr></thead><tbody>
      ${items.map(it => {
        const pending = it.status === 'pending';
        const published = it.status === 'corrected' ? it.corrected_value : it.status === 'approved' ? it.valeur : null;
        return `<tr data-q-id="${Number(it.id)}" data-q-status="${escapeHtml(it.status)}">
          <td class="mono-xs" style="padding:8px 10px;"><div class="fw-600">${escapeHtml(it.indicateur)}</div>
            <div class="text-muted">${escapeHtml(sectorName(it.secteur))} · ${escapeHtml(it.region)} · ${escapeHtml(it.date_reference)} · ${escapeHtml(it.source_api)}</div></td>
          <td class="mono-xs" style="padding:8px 10px;text-align:right;white-space:nowrap;">${escapeHtml(fmtNum(it.valeur))} ${escapeHtml(it.unite || '')}</td>
          <td class="mono-xs" style="padding:8px 10px;">${(it.flags || []).filter(f => f !== 'SUPERVISOR_REVIEW').map(f => `<span class="badge" style="color:var(--amber);border-color:var(--amber);background:transparent;margin:0 4px 4px 0;">${escapeHtml(flagLabel(f))}</span>`).join('') || escapeHtml(flagLabel('SUPERVISOR_REVIEW'))}</td>
          <td class="mono-xs" style="padding:8px 10px;min-width:230px;">${pending ? `
            <div class="flex gap-2 flex-wrap admin-q-actions">
              <button type="button" class="btn btn-cyan mono-xs admin-q-act" data-act="approve" data-id="${Number(it.id)}">${t('admin.q_approve')}</button>
              <button type="button" class="btn btn-ghost mono-xs admin-q-act" data-act="correct" data-id="${Number(it.id)}">${t('admin.q_correct')}</button>
              <button type="button" class="btn btn-ghost mono-xs admin-q-act" data-act="reject" data-id="${Number(it.id)}">${t('admin.q_reject')}</button>
            </div>` : `<div><span class="badge">${t(`admin.q_status.${it.status}`)}</span>
              ${published != null ? `<div class="text-muted">${escapeHtml(t('admin.q_published_as').replace('{value}', fmtNum(published)))}</div>` : ''}
              <div class="text-muted">${escapeHtml(it.reviewed_by || '')} · ${fmtDateTime(it.reviewed_at)}</div>
              ${it.review_note ? `<div class="text-muted">${escapeHtml(it.review_note)}</div>` : ''}</div>`}</td></tr>`;
      }).join('')}</tbody></table></div>` : `<p class="mono-sm text-muted" id="admin-q-empty">${t(_qStatus === 'pending' ? 'admin.q_empty_pending' : 'admin.q_empty')}</p>`}
  </div>`;

  const msg = document.getElementById('admin-q-msg');
  panel.querySelectorAll('.admin-q-filter').forEach(b => b.addEventListener('click', () => { _qStatus = b.dataset.status; renderPanel(); }));

  const submit = async (id, act, body) => {
    try {
      await adminFetch(`/quarantine/${id}/${act}`, { method: 'POST', body });
      showToast(t(`admin.q_done.${{ approve: 'approved', correct: 'corrected', reject: 'rejected' }[act]}`), 'success');
    } catch (err) {
      if (err.status === 401 || err.status === 403) { handlePanelError(err); return; }
      if (err.status === 409 || err.status === 404) { showToast(t('admin.q_conflict'), 'info'); }
      else { msg.textContent = `${t('admin.load_failed')}: ${err.message}`; return; }
    }
    renderPanel();
  };

  panel.querySelectorAll('.admin-q-act').forEach(btn => btn.addEventListener('click', () => {
    const id = Number(btn.dataset.id);
    if (btn.dataset.act === 'correct') {
      const cell = btn.closest('td');
      cell.innerHTML = `<div class="admin-q-form flex gap-2 flex-wrap items-center">
        <input type="number" step="any" class="admin-q-value" aria-label="${escapeHtml(t('admin.q_new_value'))}" placeholder="${escapeHtml(t('admin.q_new_value'))}" style="width:120px;">
        <input type="text" maxlength="300" class="admin-q-note" aria-label="${escapeHtml(t('admin.q_note'))}" placeholder="${escapeHtml(t('admin.q_note'))}" style="width:160px;">
        <button type="button" class="btn btn-cyan mono-xs admin-q-confirm">${t('admin.q_confirm')}</button>
        <button type="button" class="btn btn-ghost mono-xs admin-q-cancel">${t('admin.q_cancel')}</button></div>`;
      cell.querySelector('.admin-q-cancel').addEventListener('click', renderPanel);
      cell.querySelector('.admin-q-confirm').addEventListener('click', () => {
        const raw = cell.querySelector('.admin-q-value').value.trim();
        const value = Number(raw);
        if (raw === '' || !Number.isFinite(value)) { msg.textContent = t('admin.q_need_value'); return; }
        submit(id, 'correct', { value, note: cell.querySelector('.admin-q-note').value.trim() || null });
      });
      cell.querySelector('.admin-q-value').focus();
      return;
    }
    submit(id, btn.dataset.act, {});
  }));
}

/* ── Shared helpers for the management tabs ─────────────────────────────── */

const fill = (txt, vars) => Object.entries(vars).reduce((acc, [k, v]) => acc.replace(`{${k}}`, String(v)), txt);

/** Run a mutating call; on success toast + reload, on 404/409 explain and reload, otherwise show the message. */
async function mutate(path, body, okKey, msgEl, goneKey) {
  try {
    await adminFetch(path, { method: 'POST', body });
    showToast(t(okKey), 'success');
  } catch (err) {
    if (err.status === 401 || err.status === 403) { handlePanelError(err); return; }
    if ((err.status === 404 || err.status === 409) && goneKey) { showToast(t(goneKey), 'info'); }
    else { msgEl.textContent = `${t('admin.load_failed')}: ${err.message}`; return; }
  }
  renderPanel();
}

/* ── Data: find, correct, delete, restore ────────────────────────────────── */

async function loadData(panel) {
  const params = new URLSearchParams({ limit: '50' });
  if (_dSector) params.set('sector', _dSector);
  if (_dQuery) params.set('q', _dQuery);
  const [found, gone] = await Promise.all([adminFetch(`/data?${params}`), adminFetch('/data/deleted?limit=20')]);
  const items = found.items || [];
  const deleted = gone.items || [];
  panel.innerHTML = `
    <div class="card mb-4" style="padding:16px;">
      <h4 class="mono-sm uppercase mb-2">${t('admin.d_title')}</h4>
      <p class="mono-xs text-muted mb-3">${t('admin.d_desc')}</p>
      <form class="flex gap-2 flex-wrap mb-3" id="admin-d-form">
        <select id="admin-d-sector" class="mono-xs" aria-label="${escapeHtml(t('admin.d_sector_all'))}">
          <option value="">${t('admin.d_sector_all')}</option>
          ${SECTOR_IDS.map(id => `<option value="${id}" ${id === _dSector ? 'selected' : ''}>${escapeHtml(sectorName(id))}</option>`).join('')}
        </select>
        <input type="search" id="admin-d-q" class="mono-xs" maxlength="100" value="${escapeHtml(_dQuery)}" placeholder="${escapeHtml(t('admin.d_search_ph'))}" style="min-width:220px;">
        <button class="btn btn-cyan mono-xs" type="submit">${t('admin.d_search')}</button>
      </form>
      <p class="mono-xs mb-2" id="admin-d-msg" role="status"></p>
      ${items.length ? `<div style="overflow-x:auto;"><table class="ds-table" id="admin-d-table"><thead><tr>
        <th class="mono-xs text-muted" style="text-align:left;padding:6px 10px;">${t('admin.d_th_obs')}</th>
        <th class="mono-xs text-muted" style="text-align:right;padding:6px 10px;">${t('admin.d_th_value')}</th>
        <th class="mono-xs text-muted" style="text-align:left;padding:6px 10px;">${t('admin.d_th_actions')}</th></tr></thead><tbody>
        ${items.map(o => `<tr data-d-id="${Number(o.id)}">
          <td class="mono-xs" style="padding:8px 10px;"><div class="fw-600">${escapeHtml(o.indicator)}</div>
            <div class="text-muted">${escapeHtml(sectorName(o.sector))} · ${escapeHtml(o.region)} · ${escapeHtml(o.reference_date)} · ${escapeHtml(o.source)}</div>
            ${o.approved_by && o.approved_by !== 'FreeDatatd DS Engine' ? `<div class="text-muted">${escapeHtml(o.approved_by)}</div>` : ''}</td>
          <td class="mono-xs" style="padding:8px 10px;text-align:right;white-space:nowrap;">${escapeHtml(fmtNum(o.value))} ${escapeHtml(o.unit || '')}</td>
          <td class="mono-xs admin-d-cell" style="padding:8px 10px;min-width:260px;">
            <div class="flex gap-2 flex-wrap">
              <button type="button" class="btn btn-ghost mono-xs admin-d-act" data-act="correct" data-id="${Number(o.id)}">${t('admin.d_correct')}</button>
              <button type="button" class="btn btn-ghost mono-xs admin-d-act" data-act="delete" data-id="${Number(o.id)}">${t('admin.d_delete')}</button>
            </div></td></tr>`).join('')}</tbody></table></div>` : `<p class="mono-sm text-muted" id="admin-d-empty">${t('admin.d_none')}</p>`}
    </div>
    <div class="card" style="padding:16px;">
      <h4 class="mono-sm uppercase mb-2">${t('admin.d_deleted_title')}</h4>
      <p class="mono-xs text-muted mb-3">${t('admin.d_deleted_desc')}</p>
      ${deleted.length ? `<div style="overflow-x:auto;"><table class="ds-table" id="admin-d-deleted"><tbody>
        ${deleted.map(d => `<tr data-a-id="${Number(d.id)}">
          <td class="mono-xs" style="padding:8px 10px;"><div class="fw-600">${escapeHtml(d.row.indicator)} — ${escapeHtml(fmtNum(d.row.value))} ${escapeHtml(d.row.unit || '')}</div>
            <div class="text-muted">${escapeHtml(sectorName(d.row.sector))} · ${escapeHtml(d.row.region)} · ${escapeHtml(d.row.reference_date)}</div>
            <div class="text-muted">${fmtDateTime(d.deleted_at)} ${escapeHtml(fill(t('admin.d_by'), { who: d.deleted_by }))} — ${escapeHtml(d.reason)}</div></td>
          <td style="padding:8px 10px;"><button type="button" class="btn btn-ghost mono-xs admin-d-restore" data-id="${Number(d.id)}">${t('admin.d_restore')}</button></td></tr>`).join('')}
        </tbody></table></div>` : `<p class="mono-sm text-muted" id="admin-d-nodeleted">${t('admin.d_deleted_none')}</p>`}
    </div>`;

  const msg = document.getElementById('admin-d-msg');
  document.getElementById('admin-d-form').addEventListener('submit', (e) => {
    e.preventDefault();
    _dSector = document.getElementById('admin-d-sector').value;
    _dQuery = document.getElementById('admin-d-q').value.trim();
    renderPanel();
  });
  panel.querySelectorAll('.admin-d-restore').forEach(b => b.addEventListener('click', () =>
    mutate(`/data/deleted/${Number(b.dataset.id)}/restore`, {}, 'admin.d_restored', msg, 'admin.d_gone')));

  panel.querySelectorAll('.admin-d-act').forEach(btn => btn.addEventListener('click', () => {
    const id = Number(btn.dataset.id);
    const cell = btn.closest('td');
    const isCorrect = btn.dataset.act === 'correct';
    cell.innerHTML = `<div class="admin-d-form flex gap-2 flex-wrap items-center">
      ${isCorrect ? `<input type="number" step="any" class="admin-d-value" aria-label="${escapeHtml(t('admin.d_new_value'))}" placeholder="${escapeHtml(t('admin.d_new_value'))}" style="width:120px;">` : ''}
      <input type="text" maxlength="300" class="admin-d-reason" aria-label="${escapeHtml(t('admin.d_reason_ph'))}" placeholder="${escapeHtml(t('admin.d_reason_ph'))}" style="width:190px;">
      <button type="button" class="btn ${isCorrect ? 'btn-cyan' : 'btn-ghost'} mono-xs admin-d-confirm" ${isCorrect ? '' : 'style="color:var(--red);border-color:var(--red);"'}>${t(isCorrect ? 'admin.d_confirm_correct' : 'admin.d_confirm_delete')}</button>
      <button type="button" class="btn btn-ghost mono-xs admin-d-cancel">${t('admin.d_cancel')}</button></div>`;
    cell.querySelector('.admin-d-cancel').addEventListener('click', renderPanel);
    cell.querySelector('.admin-d-confirm').addEventListener('click', () => {
      const reason = cell.querySelector('.admin-d-reason').value.trim();
      if (reason.length < 3) { msg.textContent = t('admin.d_need_reason'); return; }
      if (isCorrect) {
        const raw = cell.querySelector('.admin-d-value').value.trim();
        const value = Number(raw);
        if (raw === '' || !Number.isFinite(value)) { msg.textContent = t('admin.d_need_value'); return; }
        mutate(`/data/${id}/correct`, { value, reason }, 'admin.d_corrected', msg, 'admin.d_gone');
      } else {
        mutate(`/data/${id}/delete`, { reason }, 'admin.d_deleted', msg, 'admin.d_gone');
      }
    });
    cell.querySelector(isCorrect ? '.admin-d-value' : '.admin-d-reason').focus();
  }));
}

/* ── AI reports ──────────────────────────────────────────────────────────── */

async function loadReports(panel) {
  const { items } = await adminFetch('/reports?limit=50');
  panel.innerHTML = `<div class="card" style="padding:16px;">
    <h4 class="mono-sm uppercase mb-2">${t('admin.r_title')}</h4>
    <p class="mono-xs text-muted mb-3">${t('admin.r_desc')}</p>
    <p class="mono-xs mb-2" id="admin-r-msg" role="status"></p>
    ${items.length ? items.map(r => `<div class="mb-3 admin-r-item" data-r-id="${Number(r.id)}" style="border-top:1px solid var(--border);padding-top:10px;">
      <div class="flex justify-between flex-wrap gap-2 items-center">
        <div class="mono-xs"><span class="fw-600">${r.sector ? escapeHtml(sectorName(r.sector)) : escapeHtml(t('admin.d_sector_all'))}</span>
          · ${fmtDateTime(r.created_at)} · ${escapeHtml(r.model || '')} · ${escapeHtml(fill(t('admin.r_obs'), { n: Number(r.observations_used || 0) }))}</div>
        <div class="admin-r-cell"><button type="button" class="btn btn-ghost mono-xs admin-r-del" data-id="${Number(r.id)}">${t('admin.r_delete')}</button></div>
      </div>
      <details class="mt-2"><summary class="mono-xs text-cyan" style="cursor:pointer;">${t('admin.r_show')}</summary>
        <pre class="mono-xs" style="white-space:pre-wrap;margin-top:8px;">${escapeHtml(r.report || '')}</pre></details></div>`).join('')
      : `<p class="mono-sm text-muted" id="admin-r-empty">${t('admin.r_none')}</p>`}
  </div>`;
  const msg = document.getElementById('admin-r-msg');
  panel.querySelectorAll('.admin-r-del').forEach(btn => btn.addEventListener('click', () => {
    const id = Number(btn.dataset.id);
    const cell = btn.closest('.admin-r-cell');
    cell.innerHTML = `<div class="flex gap-2 flex-wrap items-center">
      <input type="text" maxlength="300" class="admin-r-reason" aria-label="${escapeHtml(t('admin.d_reason_ph'))}" placeholder="${escapeHtml(t('admin.d_reason_ph'))}" style="width:190px;">
      <button type="button" class="btn btn-ghost mono-xs admin-r-confirm" style="color:var(--red);border-color:var(--red);">${t('admin.d_confirm_delete')}</button>
      <button type="button" class="btn btn-ghost mono-xs admin-r-cancel">${t('admin.d_cancel')}</button></div>`;
    cell.querySelector('.admin-r-cancel').addEventListener('click', renderPanel);
    cell.querySelector('.admin-r-confirm').addEventListener('click', () => {
      const reason = cell.querySelector('.admin-r-reason').value.trim();
      if (reason.length < 3) { msg.textContent = t('admin.d_need_reason'); return; }
      mutate(`/reports/${id}/delete`, { reason }, 'admin.r_deleted', msg, 'admin.d_gone');
    });
    cell.querySelector('.admin-r-reason').focus();
  }));
}

/* ── Team (owners manage it) ─────────────────────────────────────────────── */

async function loadTeam(panel) {
  const { admins, can_manage: canManage } = await adminFetch('/admins');
  panel.innerHTML = `<div class="card" style="padding:16px;">
    <h4 class="mono-sm uppercase mb-2">${t('admin.tm_title')}</h4>
    <p class="mono-xs text-muted mb-3">${t('admin.tm_desc')}</p>
    <div style="overflow-x:auto;"><table class="ds-table" id="admin-team-table"><thead><tr>
      <th class="mono-xs text-muted" style="text-align:left;padding:6px 10px;">${t('admin.tm_th_email')}</th>
      <th class="mono-xs text-muted" style="text-align:left;padding:6px 10px;">${t('admin.tm_th_role')}</th>
      <th class="mono-xs text-muted" style="text-align:left;padding:6px 10px;">${t('admin.tm_th_added')}</th>
      <th></th></tr></thead><tbody>
      ${admins.map(a => `<tr data-email="${escapeHtml(a.email)}">
        <td class="mono-xs" style="padding:8px 10px;">${escapeHtml(a.email)}</td>
        <td class="mono-xs" style="padding:8px 10px;"><span class="badge badge--cyan">${escapeHtml(t(`admin.tm_roles.${a.role}`))}</span>${a.permanent ? ` <span class="text-muted">${t('admin.tm_permanent')}</span>` : ''}</td>
        <td class="mono-xs text-muted" style="padding:8px 10px;">${escapeHtml(a.added_by || '')}</td>
        <td style="padding:8px 10px;">${canManage && !a.permanent && a.email !== _me.email ? `<button type="button" class="btn btn-ghost mono-xs admin-team-remove" data-email="${escapeHtml(a.email)}">${t('admin.tm_remove')}</button>` : ''}</td></tr>`).join('')}
    </tbody></table></div>
    <p class="mono-xs mt-3" id="admin-team-msg" role="status"></p>
    ${canManage ? `<form class="flex gap-2 flex-wrap mt-3" id="admin-team-form">
        <input type="email" id="admin-team-email" class="mono-xs" maxlength="254" required placeholder="${escapeHtml(t('admin.tm_add_ph'))}" aria-label="${escapeHtml(t('admin.tm_add_ph'))}" style="min-width:280px;">
        <button class="btn btn-cyan mono-xs" type="submit">${t('admin.tm_add')}</button></form>
      <p class="mono-xs text-muted mt-2">${t('admin.tm_hint')}</p>`
      : `<p class="mono-xs text-muted mt-3" id="admin-team-readonly">${t('admin.tm_owner_only')}</p>`}
  </div>`;
  const msg = document.getElementById('admin-team-msg');
  document.getElementById('admin-team-form')?.addEventListener('submit', (e) => {
    e.preventDefault();
    const email = document.getElementById('admin-team-email').value.trim();
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) { msg.textContent = t('admin.tm_invalid'); return; }
    mutate('/admins', { email }, 'admin.tm_added', msg, null);
  });
  panel.querySelectorAll('.admin-team-remove').forEach(btn => btn.addEventListener('click', () => {
    if (!window.confirm(fill(t('admin.tm_confirm_remove'), { email: btn.dataset.email }))) return;
    mutate('/admins/remove', { email: btn.dataset.email }, 'admin.tm_removed', msg, null);
  }));
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
