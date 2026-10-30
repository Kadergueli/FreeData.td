/**
 * View: Infrastructure status.
 * Everything shown is measured: health, audit counts, and the real scheduler state.
 * (The former 24h "load" chart and "Charge Maximale : Optimale" were invented.)
 */

import { fetchHealth, fetchAudit, fetchSourcesFreshness } from '../api_client.js';
import { formatScore, formatCount } from '../ui.js';
import { t } from '../i18n.js';
import { escapeHtml } from '../sanitize.js';

function formatAuditAgent(agent) {
  if (!agent) return t('status.agent_cleaning');
  const a = String(agent);
  if (a.includes('Agent 2') || a.includes('Data Science')) return t('status.agent_cleaning');
  if (a.includes('Agent 1')) return t('status.agent_ingestion');
  if (a.includes('Agent 3')) return t('status.agent_publication');
  return a.replace(/Agent/g, 'Agent ').trim();
}

function formatAuditOp(op) {
  if (!op) return t('status.op_default');
  const o = String(op);
  if (o === 'ds_clean') return t('status.op_clean');
  if (o === 'raw_ingest') return t('status.op_raw');
  return o;
}

function formatDateTime(raw) {
  if (!raw) return '—';
  const d = new Date(raw);
  if (isNaN(d.getTime())) return String(raw).split('.')[0].replace('T', ' ');
  return d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit' })
    + ' · ' + d.toLocaleDateString(undefined, { day: '2-digit', month: 'short', year: 'numeric' });
}

function formatAuditPayload(val) {
  if (!val) return '';
  const parts = String(val).split('=');
  if (parts.length === 2) {
    return `${escapeHtml(parts[0].trim())} = <strong class="text-cyan">${escapeHtml(parts[1].trim())}</strong>`;
  }
  return escapeHtml(val);
}

function skeletonRow(w1, w2) {
  return `<div class="flex justify-between items-center gap-3" style="padding:8px 12px;border-bottom:1px solid var(--border);background:var(--bg);border-radius:4px;">
    <div class="flex items-center gap-2" style="flex:1;"><span class="skeleton" style="width:${w1}px;height:16px;"></span><span class="skeleton" style="width:${w2}px;height:16px;"></span></div>
    <span class="skeleton" style="width:70px;height:16px;"></span></div>`;
}

function renderScheduler(sch) {
  const box = document.getElementById('scheduler-body');
  if (!box) return;
  if (!sch) { box.innerHTML = `<p class="mono-xs text-muted">—</p>`; return; }

  const state = sch.job_running ? t('status.sched_running_now')
    : (sch.is_running ? t('status.sched_active') : t('status.sched_stopped'));
  const last = sch.last_result;
  let lastLine = t('status.sched_never');
  let sectors = '';
  if (sch.last_run) {
    lastLine = formatDateTime(sch.last_run);
    if (last && typeof last.total_stored === 'number') {
      lastLine += ` — ${t('status.sched_stored').replace('{n}', last.total_stored.toLocaleString())}`;
    }
  }
  if (last && last.sectors && Object.keys(last.sectors).length) {
    sectors = `<div class="mono-xs text-muted uppercase mt-4 mb-2">${t('status.sched_sectors')}</div>
      <div class="flex gap-2 flex-wrap">` + Object.entries(last.sectors).map(([id, r]) => {
        const failed = !r || r.error;
        const n = failed ? t('status.sched_error') : (typeof r.stored === 'number' ? r.stored : '—');
        return `<span class="badge ${failed ? '' : 'badge--valid'} mono-xs" data-sector="${escapeHtml(id)}">${escapeHtml(t(`sectors.names.${id}`))} · ${escapeHtml(n)}</span>`;
      }).join('') + `</div>`;
  }

  box.innerHTML = `
    <div class="grid-2">
      <div><div class="mono-xs text-muted uppercase mb-1">${t('status.sched_state')}</div>
        <div class="mono-md fw-700" id="sched-state">${escapeHtml(state)}</div></div>
      <div><div class="mono-xs text-muted uppercase mb-1">${t('status.sched_interval')}</div>
        <div class="mono-md fw-700">${escapeHtml(t('status.sched_hours').replace('{h}', sch.interval_hours))}</div></div>
      <div><div class="mono-xs text-muted uppercase mb-1">${t('status.sched_last')}</div>
        <div class="mono-sm" id="sched-last">${escapeHtml(lastLine)}</div></div>
      <div><div class="mono-xs text-muted uppercase mb-1">${t('status.sched_next')}</div>
        <div class="mono-sm" id="sched-next">${escapeHtml(formatDateTime(sch.next_run))}</div></div>
    </div>${sectors}`;
}

function renderFreshness(sources) {
  const box = document.getElementById('freshness-body');
  if (!box) return;
  if (!sources) { box.innerHTML = `<p class="mono-xs text-muted">${t('status.fresh_unavailable')}</p>`; return; }
  if (!sources.length) { box.innerHTML = `<p class="mono-xs text-muted">${t('status.fresh_none')}</p>`; return; }
  const badge = { ok: 'badge--valid', late: '', stale: '' };
  box.innerHTML = `
    <p class="body-text mb-3" style="font-size:12px;">${t('status.fresh_intro')}</p>
    <div class="flex flex-col gap-2">${sources.map(s => `
      <div class="flex justify-between items-center gap-3 status-row" data-source-status="${escapeHtml(s.status)}"
           style="padding:8px 12px;border-bottom:1px solid var(--border);background:var(--bg);border-radius:4px;">
        <div style="min-width:0;flex:1;">
          <span class="mono-xs fw-700">${escapeHtml(s.source)}</span>
          <span class="mono-xs text-muted"> · ${escapeHtml(t(`sectors.names.${s.sector}`))} · ${formatCount(s.rows)} ${t('common.records')}</span>
        </div>
        <span class="mono-xs text-muted" style="flex-shrink:0;">${t('status.fresh_latest')} : ${escapeHtml(s.latest_reference || '—')}</span>
        <span class="badge ${badge[s.status] || ''} mono-xs" style="flex-shrink:0;">${t(`status.fresh_${s.status}`)}</span>
      </div>`).join('')}</div>`;
}

export const StatusView = {
  render() {
    return `
      <div class="flex justify-between items-start mb-6 page-head">
        <div>
          <div class="mono-xs text-muted fw-700 mb-1 flex items-center gap-1">
            <i data-lucide="activity" style="width:14px;height:14px;"></i> ${t('status.surveillance')}
          </div>
          <h2 class="hero-title uppercase text-accent" style="font-size:24px;">${t('status.title')}</h2>
        </div>
        <div class="mono-xs text-muted flex items-center gap-1" id="status-storage-backend">
          <i data-lucide="database" style="width:12px;height:12px;"></i> ${t('status.storage')} : ${t('common.loading')}
        </div>
      </div>

      <div class="grid-2 mb-6">
        <div class="card" style="padding:16px;">
          <h4 class="mono-xs text-muted uppercase mb-2">${t('home.stat_score')}</h4>
          <div class="mono-2xl fw-700 mb-1" id="status-val-score"><span class="skeleton"></span></div>
          <div class="mono-xs text-muted fw-700 flex items-center gap-1" id="status-val-trend">
            <i data-lucide="shield-check" style="width:14px;height:14px;"></i> ${t('status.audit_label')}
          </div>
        </div>
        <div class="card" style="padding:16px;">
          <h4 class="mono-xs text-muted uppercase mb-2">${t('home.stat_obs')}</h4>
          <div class="mono-2xl fw-700 mb-1" id="status-total-obs"><span class="skeleton"></span></div>
          <div class="mono-xs text-accent fw-700 flex items-center gap-1" id="status-anomalies-count">
            <i data-lucide="alert-circle" style="width:14px;height:14px;"></i> ${t('status.anomalies')} : —
          </div>
        </div>
      </div>

      <h4 class="uppercase mb-4 flex items-center gap-2" style="font-size:14px;">
        <i data-lucide="git-branch" style="width:16px;height:16px;" class="text-cyan"></i> ${t('status.pipelines_title')} (${t('status.live_db')})
      </h4>

      <div class="flex flex-col gap-3 mb-6" id="pipeline-cards-container">
        ${[['table', 'raw'], ['check-square', 'clean'], ['globe', 'public']].map(([icon, k]) => `
        <div class="card pipeline-card">
          <div class="flex justify-between items-start mb-2">
            <h5 class="uppercase flex items-center gap-2" style="font-size:14px;">
              <i data-lucide="${icon}" style="width:14px;height:14px;"></i> ${t(`status.${k}_title`)}
            </h5>
            <span class="mono-sm fw-700" id="${k}-count-tag"><span class="skeleton"></span></span>
          </div>
          <p class="body-text" style="font-size:12px;">${t(`status.${k}_desc`)}</p>
        </div>`).join('')}
      </div>

      <div class="card mb-6" style="padding:16px;border-color:var(--border-strong);">
        <h4 class="mono-sm uppercase mb-4 text-cyan flex items-center gap-2">
          <i data-lucide="list-checks" style="width:16px;height:16px;"></i> ${t('status.audit_logs')}
        </h4>
        <div class="flex flex-col gap-2" id="audit-logs-list" style="min-height:140px;max-height:220px;overflow-y:auto;">
          ${skeletonRow(120, 100)}${skeletonRow(140, 110)}${skeletonRow(110, 90)}
        </div>
      </div>

      <div class="card mb-6" style="padding:16px;border-color:var(--border-strong);">
        <h4 class="mono-sm uppercase mb-4 flex items-center gap-2">
          <i data-lucide="calendar-check" style="width:16px;height:16px;"></i> ${t('status.fresh_title')}
        </h4>
        <div id="freshness-body"><span class="skeleton" style="width:240px;"></span></div>
      </div>

      <div class="card mb-6" style="padding:16px;border-color:var(--border-strong);">
        <h4 class="mono-sm uppercase mb-4 flex items-center gap-2">
          <i data-lucide="clock" style="width:16px;height:16px;"></i> ${t('status.sched_title')}
        </h4>
        <div id="scheduler-body"><span class="skeleton" style="width:240px;"></span></div>
      </div>
    `;
  },

  async init() {
    if (window.lucide) window.lucide.createIcons();

    const [health, audit, freshness] = await Promise.all([
      fetchHealth().catch(() => null),
      fetchAudit().catch(() => null),
      fetchSourcesFreshness().catch(() => null),
    ]);
    renderFreshness(freshness);

    const backendEl = document.getElementById('status-storage-backend');
    if (backendEl) {
      backendEl.innerHTML = health
        ? `<i data-lucide="database" style="width:12px;height:12px;"></i> ${t('status.storage')} : ${escapeHtml(String(health.storage_backend || '—').toUpperCase())} | ${t('status.api_ok')}`
        : `<i data-lucide="database" style="width:12px;height:12px;"></i> ${t('status.storage')} : — | ${t('status.api_down')}`;
    }
    renderScheduler(health ? health.scheduler : null);

    const rep = audit && audit.reports_summary;
    const scoreEl = document.getElementById('status-val-score');
    const obsEl = document.getElementById('status-total-obs');
    const anomaliesEl = document.getElementById('status-anomalies-count');
    if (scoreEl) scoreEl.textContent = rep ? formatScore(rep) : '—';
    if (obsEl) obsEl.textContent = rep && rep.total_public != null
      ? `${formatCount(rep.total_public)} ${t('common.records')}` : '—';
    if (anomaliesEl) anomaliesEl.innerHTML = `<i data-lucide="alert-circle" style="width:14px;height:14px;"></i> ${t('status.anomalies')} : ${rep && rep.nb_anomalies != null ? formatCount(rep.nb_anomalies) : '—'}`;

    [['raw', 'total_raw'], ['clean', 'total_clean'], ['public', 'total_public']].forEach(([k, f]) => {
      const el = document.getElementById(`${k}-count-tag`);
      if (el) el.textContent = rep && rep[f] != null ? `${formatCount(rep[f])} ${t('common.records')}` : '—';
    });

    const logs = document.getElementById('audit-logs-list');
    if (logs) {
      if (audit && Array.isArray(audit.logs) && audit.logs.length > 0) {
        logs.innerHTML = audit.logs.map(log => `
          <div class="flex justify-between items-center gap-3 status-row" style="padding:8px 12px;border-bottom:1px solid var(--border);background:var(--bg);border-radius:4px;margin-bottom:4px;">
            <div class="flex items-center gap-2 status-log-main" style="min-width:0;flex:1;">
              <span class="badge" style="background:#eff6ff;color:#1e40af;border-color:#bfdbfe;font-size:11px;padding:2px 8px;flex-shrink:0;">
                <i data-lucide="shield-check" style="width:12px;height:12px;display:inline-block;vertical-align:-1px;"></i> ${escapeHtml(formatAuditAgent(log.agent))}
              </span>
              <span class="mono-xs fw-600 text-muted" style="flex-shrink:0;">${escapeHtml(formatAuditOp(log.type_operation))}</span>
              <span class="mono-xs status-log-payload" style="color:var(--text);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${formatAuditPayload(log.valeur_apres || '')}</span>
            </div>
            <span class="mono-xs text-muted" style="font-size:11px;flex-shrink:0;">${escapeHtml(formatDateTime(log.timestamp))}</span>
          </div>`).join('');
      } else {
        logs.innerHTML = `<p class="mono-xs text-muted">${t('status.no_logs')}</p>`;
      }
    }
    if (window.lucide) window.lucide.createIcons();
  },
};
