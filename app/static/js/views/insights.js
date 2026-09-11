/**
 * View: AI Insights — Automated Exploration & Trend Analysis (DATABASE & LLM DIRECT)
 */

import { generateStudy, fetchObservations, fetchStudies, fetchCrossSector } from '../api_client.js';
import { initChartDensity } from '../charts.js';
import { t } from '../i18n.js';
import { escapeHtml } from '../sanitize.js';

let activeInsightSector = 'all';

function getInsightSectorTabs() {
  return [
    { id: 'all', label: t('insights.sectors.all') },
    { id: 'agriculture', label: t('insights.sectors.agriculture') },
    { id: 'environment', label: t('insights.sectors.environment') },
    { id: 'markets', label: t('insights.sectors.markets') },
    { id: 'economy', label: t('insights.sectors.economy') },
    { id: 'health', label: t('insights.sectors.health') },
    { id: 'energy', label: t('insights.sectors.energy') },
  ];
}

async function updateInsightsDensityChart(sector = 'all') {
  try {
    const targetSector = sector === 'all' ? null : sector;
    const obs = await fetchObservations(targetSector, 500);
    const density = {};
    if (obs && obs.length > 0) {
      obs.forEach(o => {
        const reg = (o.region || 'TCH').substring(0, 3).toUpperCase();
        if (!density[reg]) density[reg] = { total: 0, validated: 0 };
        density[reg].total += 1;
        if (o.status === 'validated' || o.status === 'VALIDÉ' || !o.status) {
          density[reg].validated += 1;
        }
      });
    }
    initChartDensity(Object.keys(density).length > 0 ? density : null);
  } catch (err) {
    console.warn('updateInsightsDensityChart error:', err);
    initChartDensity();
  }
}

/** Format an ISO-ish date string into a short, readable label. Never trusts the
 * input's shape — falls back to the raw (escaped) string if parsing fails. */
function formatStudyDate(raw) {
  if (!raw) return t('insights.unknown_date');
  const d = new Date(raw);
  if (isNaN(d.getTime())) return escapeHtml(String(raw));
  return d.toLocaleDateString(undefined, { day: '2-digit', month: 'short', year: 'numeric' });
}

/** Formats raw report markdown text into structured executive HTML. */
function formatReportMarkdown(text) {
  if (!text) return '';
  const lines = text.split('\n');
  let html = '';
  let inList = false;
  let listType = null;

  const closeList = () => {
    if (inList) {
      html += listType === 'ol' ? '</ol>' : '</ul>';
      inList = false;
      listType = null;
    }
  };

  lines.forEach(line => {
    const trimmed = line.trim();
    if (!trimmed) {
      closeList();
      return;
    }

    if (trimmed.startsWith('### ')) {
      closeList();
      const content = escapeHtml(trimmed.slice(4)).replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
      html += `<h4 class="report-heading">${content}</h4>`;
    } else if (trimmed.startsWith('## ')) {
      closeList();
      const content = escapeHtml(trimmed.slice(3)).replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
      html += `<h3 class="report-heading-lg">${content}</h3>`;
    } else if (trimmed.startsWith('# ')) {
      closeList();
      const content = escapeHtml(trimmed.slice(2)).replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
      html += `<h2 class="report-heading-xl">${content}</h2>`;
    } else if (/^\d+\.\s+/.test(trimmed)) {
      if (!inList || listType !== 'ol') {
        closeList();
        html += '<ol class="report-list">';
        inList = true;
        listType = 'ol';
      }
      const rawText = trimmed.replace(/^\d+\.\s+/, '');
      const content = escapeHtml(rawText).replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
      html += `<li>${content}</li>`;
    } else if (trimmed.startsWith('- ') || trimmed.startsWith('* ')) {
      if (!inList || listType !== 'ul') {
        closeList();
        html += '<ul class="report-list">';
        inList = true;
        listType = 'ul';
      }
      const rawText = trimmed.replace(/^[-*]\s+/, '');
      const content = escapeHtml(rawText).replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
      html += `<li>${content}</li>`;
    } else {
      closeList();
      const content = escapeHtml(trimmed).replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
      html += `<p class="report-paragraph">${content}</p>`;
    }
  });

  closeList();
  return html;
}

/** Renders the full report block — shared by "just generated" and "opened from
 * the library" code paths. All fields are escaped: they come from the LLM and/or
 * harvested external data, never trusted as HTML. */
function renderReportBlock(result) {
  const formattedReport = formatReportMarkdown(result.report || '');
  const modelName = escapeHtml(result.model || 'N/A');
  const sectorLabel = escapeHtml((result.sector || t('insights.sectors.all')).toUpperCase());
  const obsCount = escapeHtml(result.observations_used ?? 'N/A');
  const dateLabel = escapeHtml(formatStudyDate(result.created_at));
  return `
    <div class="card card--accent-border mb-4" style="padding:24px;">
      <div class="flex justify-between items-center mb-3">
        <span class="badge badge--valid">${t('insights.result_badge')}</span>
        <span class="mono-xs text-muted" style="font-weight:600;">${t('insights.result_model')}: ${modelName}</span>
      </div>
      <h4 class="mono-lg mb-1" style="font-weight:700;font-family:var(--font-sans);">${t('insights.result_title')} — ${sectorLabel}</h4>
      <p class="mono-xs text-muted mb-4">${t('insights.result_obs')}: ${obsCount} observations · ${dateLabel}</p>
      <div class="report-content">${formattedReport}</div>
    </div>
  `;
}

/** Compact row for one library entry: date, model, observation count, and an
 * honest freshness badge — never auto-regenerates, only signals the option. */
function renderStudyLibraryRow(study) {
  const dateLabel = escapeHtml(formatStudyDate(study.created_at));
  const sectorLabel = escapeHtml((study.sector || t('insights.sectors.all')).toUpperCase());
  const obsCount = escapeHtml(study.observations_used ?? 'N/A');
  const isStale = !!study.is_stale;
  const newCount = isStale ? Math.max(0, (study.live_observations_count || 0) - (study.observations_used || 0)) : 0;
  const freshnessBadge = isStale
    ? `<span class="badge" style="background:#fef3c7;color:#92400e;border-color:#fde68a;">${t('insights.stale_badge')}${newCount > 0 ? ` (+${escapeHtml(newCount)})` : ''}</span>`
    : `<span class="badge badge--valid">${t('insights.fresh_badge')}</span>`;

  return `
    <div class="card study-library-row" data-study-id="${escapeHtml(study.id)}" style="padding:14px 16px;cursor:pointer;">
      <div class="flex justify-between items-center gap-2" style="flex-wrap:wrap;">
        <div class="flex items-center gap-2" style="min-width:0;">
          <i data-lucide="file-text" style="width:14px;height:14px;flex-shrink:0;" class="text-cyan"></i>
          <span class="mono-sm fw-700">${sectorLabel}</span>
          <span class="mono-xs text-muted">${dateLabel} · ${obsCount} obs.</span>
        </div>
        <div class="flex items-center gap-2" style="flex-shrink:0;">
          ${freshnessBadge}
          <i data-lucide="chevron-down" style="width:14px;height:14px;" class="text-muted study-library-chevron"></i>
        </div>
      </div>
      <div class="study-library-detail" style="display:none;margin-top:12px;"></div>
    </div>
  `;
}

async function loadReportsLibrary(sector) {
  const listEl = document.getElementById('reports-library-list');
  const countBadge = document.getElementById('reports-library-count-badge');
  if (!listEl) return;
  listEl.innerHTML = `<p class="mono-xs text-muted flex items-center gap-2"><i data-lucide="loader" class="animate-spin" style="width:14px;height:14px;"></i> ${t('common.loading')}</p>`;
  if (window.lucide) window.lucide.createIcons();

  const targetSector = sector === 'all' ? null : sector;
  const studies = await fetchStudies(targetSector, 100);

  if (countBadge) {
    countBadge.textContent = studies ? studies.length : 0;
  }

  if (!studies || studies.length === 0) {
    listEl.innerHTML = `<p class="mono-xs text-muted">${t('insights.no_reports_yet')}</p>`;
    return;
  }

  listEl.innerHTML = studies.map(renderStudyLibraryRow).join('');
  if (window.lucide) window.lucide.createIcons();

  // Click-to-expand: view the full report inline without leaving the library,
  // and without ever calling the LLM again (this is a pure read of stored data).
  listEl.querySelectorAll('.study-library-row').forEach((row, idx) => {
    row.addEventListener('click', () => {
      const detail = row.querySelector('.study-library-detail');
      const chevron = row.querySelector('.study-library-chevron');
      const isOpen = detail.style.display !== 'none';
      if (isOpen) {
        detail.style.display = 'none';
        if (chevron) chevron.style.transform = '';
      } else {
        if (!detail.dataset.rendered) {
          detail.innerHTML = renderReportBlock(studies[idx]);
          detail.dataset.rendered = '1';
        }
        detail.style.display = 'block';
        if (chevron) chevron.style.transform = 'rotate(180deg)';
        if (window.lucide) window.lucide.createIcons();
      }
    });
  });
}

const _FRESHNESS_STATUS_STYLE = {
  fresh:    { key: 'insights.ds.status.fresh',    bg: '#d1fae5', color: '#065f46', border: '#6ee7b7' },
  recent:   { key: 'insights.ds.status.recent',   bg: '#dbeafe', color: '#1e40af', border: '#93c5fd' },
  stale:    { key: 'insights.ds.status.stale',    bg: '#fef3c7', color: '#92400e', border: '#fde68a' },
  outdated: { key: 'insights.ds.status.outdated', bg: '#fee2e2', color: '#991b1b', border: '#fca5a5' },
  no_data:  { key: 'insights.ds.status.no_data',  bg: '#f1f5f9', color: '#64748b', border: '#cbd5e1' },
};

const _STRENGTH_STYLE = {
  strong:            { key: 'insights.ds.strength.strong',            color: '#059669' },
  moderate:          { key: 'insights.ds.strength.moderate',          color: '#0284c7' },
  weak:              { key: 'insights.ds.strength.weak',              color: '#d97706' },
  none:              { key: 'insights.ds.strength.none',              color: '#94a3b8' },
  insufficient_data: { key: 'insights.ds.strength.insufficient_data', color: '#94a3b8' },
};

function formatInterpretation(c) {
  if (!c || c.strength === 'insufficient_data') {
    return t('insights.ds.interp_insufficient');
  }
  const isPos = (c.correlation || 0) >= 0;
  const dir = isPos ? t('insights.ds.dir_pos') : t('insights.ds.dir_neg');
  const str = t(`insights.ds.strength.${c.strength}`);
  const secAKey = `sectors.names.${c.sector_a}`;
  const secBKey = `sectors.names.${c.sector_b}`;
  const secA = t(secAKey) !== secAKey ? t(secAKey) : (c.sector_a || '').toUpperCase();
  const secB = t(secBKey) !== secBKey ? t(secBKey) : (c.sector_b || '').toUpperCase();
  const r = c.correlation != null ? c.correlation.toFixed(2) : '0.00';
  const unit = c.lag_months === 1 ? t('insights.ds.month') : t('insights.ds.months');
  const lagStr = c.lag_months > 0 ? t('insights.ds.lag_fmt').replace('{n}', c.lag_months).replace('{unit}', unit) : '';
  const trend = isPos ? t('insights.ds.trend_increase') : t('insights.ds.trend_decrease');

  return t('insights.ds.interp_fmt')
    .replace('{dir}', dir)
    .replace('{str}', str)
    .replace('{lag}', lagStr)
    .replace('{a}', secA)
    .replace('{b}', secB)
    .replace('{r}', r)
    .replace('{trend}', trend);
}

async function loadCrossSectorInsights(showUpdatedBadge = false) {
  const container = document.getElementById('ds-insights-section');
  if (!container) return;

  const data = await fetchCrossSector();
  if (!data) {
    container.innerHTML = '';
    return;
  }

  // ─── 1. Freshness Scores ───────────────────────────────────────────────────
  const freshness = data.freshness || {};
  const freshnessRows = Object.entries(freshness).map(([sector, info]) => {
    const st = _FRESHNESS_STATUS_STYLE[info.status] || _FRESHNESS_STATUS_STYLE.no_data;
    const score = typeof info.freshness_score === 'number' ? info.freshness_score : 0;
    const barPct = Math.round(score * 100);
    const daysSuffix = t('insights.ds.days_suffix');
    const obsSuffix = t('insights.ds.obs_suffix');
    const daysText = info.days_ago != null ? `${info.days_ago}${daysSuffix}` : '—';
    const obsText = info.obs_count ? `${info.obs_count} ${obsSuffix}` : `0 ${obsSuffix}`;
    const statusLabel = t(st.key);
    const sectorKey = `sectors.names.${sector}`;
    const sectorLabel = t(sectorKey) !== sectorKey ? t(sectorKey) : sector.toUpperCase();

    return `
      <div class="ds-freshness-row">
        <span class="mono-xs fw-700" style="text-transform:uppercase;letter-spacing:.04em;">${escapeHtml(sectorLabel)}</span>
        <div class="ds-freshness-bar-col" style="background:var(--bg-alt);border-radius:4px;height:8px;overflow:hidden;">
          <div style="width:${barPct}%;height:100%;background:${st.color};border-radius:4px;transition:width .4s;"></div>
        </div>
        <span class="mono-xs text-muted ds-freshness-meta" style="white-space:nowrap;">${daysText} · ${obsText}</span>
        <span class="badge ds-freshness-badge" style="background:${st.bg};color:${st.color};border-color:${st.border};font-size:11px;padding:2px 8px;white-space:nowrap;">${escapeHtml(statusLabel)}</span>
      </div>`;
  }).join('');

  // ─── 2. Cross-Sector Correlations ─────────────────────────────────────────
  const correlations = data.correlations || [];
  const corrRows = correlations.map(c => {
    const ss = _STRENGTH_STYLE[c.strength] || _STRENGTH_STYLE.none;
    const rVal = c.correlation != null ? c.correlation.toFixed(3) : '—';
    const unitLabel = c.lag_months === 1 ? t('insights.ds.month') : t('insights.ds.months');
    const lagLabel = c.lag_months > 0 ? `+${c.lag_months} ${unitLabel}` : t('insights.ds.no_lag');
    const interp = formatInterpretation(c);
    const secAKey = `sectors.names.${c.sector_a}`;
    const secBKey = `sectors.names.${c.sector_b}`;
    const secAName = t(secAKey) !== secAKey ? t(secAKey) : (c.sector_a || '').toUpperCase();
    const secBName = t(secBKey) !== secBKey ? t(secBKey) : (c.sector_b || '').toUpperCase();
    const strengthLabel = t(ss.key);

    return `
      <tr>
        <td class="mono-xs fw-600" style="padding:8px 10px;text-transform:uppercase;white-space:nowrap;">${escapeHtml(secAName)}</td>
        <td class="mono-xs" style="padding:8px 4px;color:var(--text-muted);">→</td>
        <td class="mono-xs fw-600" style="padding:8px 10px;text-transform:uppercase;white-space:nowrap;">${escapeHtml(secBName)}</td>
        <td class="mono-xs" style="padding:8px 10px;text-align:center;font-weight:700;color:${ss.color};">${rVal}</td>
        <td style="padding:8px 10px;"><span class="badge" style="color:${ss.color};border-color:${ss.color};background:transparent;font-size:10px;">${escapeHtml(strengthLabel)}</span></td>
        <td class="mono-xs text-muted" style="padding:8px 10px;white-space:nowrap;">${escapeHtml(lagLabel)}</td>
        <td class="mono-xs text-muted ds-interp" style="padding:8px 10px;font-size:11px;">${escapeHtml(interp)}</td>
      </tr>`;
  }).join('');

  // ─── 3. Spatial Coverage badge ────────────────────────────────────────────
  const spatial = data.spatial_coverage || {};
  const covPct = spatial.coverage_rate != null ? Math.round(spatial.coverage_rate * 100) : 0;

  const now = new Date();
  const lastRefreshed = now.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit' });

  const refreshedBadge = showUpdatedBadge
    ? `<span class="badge badge--valid" style="font-size:10px;padding:2px 6px;">✓ ${t('insights.ds.refreshed_at')} ${escapeHtml(lastRefreshed)}</span>`
    : '';

  container.innerHTML = `
    <div class="card ds-card mb-4" style="padding:16px;border-color:var(--border-strong);">
      <div class="flex justify-between items-center ds-header mb-3">
        <h4 class="mono-sm uppercase flex items-center gap-2" style="color:var(--accent);margin:0;">
          <i data-lucide="activity" style="width:16px;height:16px;"></i> ${t('insights.ds.freshness_title')}
        </h4>
        <div class="flex items-center gap-2 ds-header-actions" style="flex-wrap:wrap;">
          ${refreshedBadge}
          <span class="mono-xs text-muted">${escapeHtml(String(data.total_observations_analyzed || 0))} ${t('insights.ds.obs_suffix')} · ${escapeHtml(lastRefreshed)}</span>
          <button id="btn-refresh-ds-insights" class="btn btn-ghost mono-xs flex items-center gap-1" style="padding:4px 10px;border-radius:6px;" title="${t('insights.ds.refresh_btn')}">
            <i data-lucide="refresh-cw" id="refresh-ds-icon" style="width:13px;height:13px;"></i> ${t('insights.ds.refresh_btn')}
          </button>
        </div>
      </div>
      ${freshnessRows}
    </div>

    <div class="card ds-card mb-4" style="padding:16px;border-color:var(--border-strong);">
      <h4 class="mono-sm uppercase mb-3 flex items-center gap-2 ds-header" style="color:var(--cyan);">
        <i data-lucide="git-merge" style="width:16px;height:16px;"></i> ${t('insights.ds.correlations_title')}
        <span class="mono-xs text-muted fw-400 ds-spatial-coverage" style="margin-left:auto;">${t('insights.ds.spatial_coverage')} : ${covPct}% (${escapeHtml(String(spatial.total_regions || 0))} / 23 ${t('insights.ds.provinces')})</span>
      </h4>
      <div style="overflow-x:auto;">
        <table class="ds-table">
          <thead>
            <tr>
              <th class="mono-xs text-muted" style="padding:6px 10px;text-align:left;white-space:nowrap;">${t('insights.ds.th_sector_a')}</th>
              <th></th>
              <th class="mono-xs text-muted" style="padding:6px 10px;text-align:left;white-space:nowrap;">${t('insights.ds.th_sector_b')}</th>
              <th class="mono-xs text-muted" style="padding:6px 10px;text-align:center;">r</th>
              <th class="mono-xs text-muted" style="padding:6px 10px;">${t('insights.ds.th_strength')}</th>
              <th class="mono-xs text-muted" style="padding:6px 10px;white-space:nowrap;">${t('insights.ds.th_lag')}</th>
              <th class="mono-xs text-muted" style="padding:6px 10px;">${t('insights.ds.th_interpretation')}</th>
            </tr>
          </thead>
          <tbody>${corrRows}</tbody>
        </table>
      </div>
    </div>
  `;

  if (window.lucide) window.lucide.createIcons();

  // Wire up the refresh button — re-runs the full DS fetch + render cycle with feedback badge!
  const refreshBtn = document.getElementById('btn-refresh-ds-insights');
  if (refreshBtn) {
    refreshBtn.addEventListener('click', async () => {
      refreshBtn.disabled = true;
      refreshBtn.innerHTML = `<i data-lucide="refresh-cw" style="width:13px;height:13px;" class="animate-spin"></i> ${t('insights.ds.refreshing')}`;
      if (window.lucide) window.lucide.createIcons();
      await loadCrossSectorInsights(true);
    });
  }
}

export const InsightsView = {
  render() {
    const tabs = getInsightSectorTabs();

    return `
      <div class="flex justify-between items-start mb-6">
        <div>
          <div class="mono-xs text-cyan mb-1 flex items-center gap-1">
            <i data-lucide="terminal" style="width:14px;height:14px;"></i> ${t('insights.agent_log')}
          </div>
          <h2 class="hero-title uppercase" style="font-size:24px;margin-bottom:4px;">${t('insights.title')}</h2>
          <p class="mono-xs text-muted uppercase">${t('insights.subtitle')}</p>
        </div>
        <div class="mono-xs text-green flex items-center gap-1" id="agent-status-tag">
          <i data-lucide="check-circle-2" style="width:14px;height:14px;"></i> ${t('insights.status_active')}
        </div>
      </div>

      <div style="border-top:1px solid var(--border);border-bottom:1px solid var(--border);padding:12px 0;" class="flex gap-2 mb-6 scrollable-tabs" id="insights-sector-tabs">
        ${tabs.map((s, i) =>
          `<button class="btn ${i === 0 ? 'btn-cyan' : 'btn-ghost'} insights-tab-btn mono-sm" data-sector="${s.id}" style="padding:6px 12px;">${s.label}</button>`
        ).join('')}
      </div>

      <!-- Density Chart -->
      <div class="card mb-6" style="padding:16px;border-color:var(--border-strong);">
        <h4 class="mono-sm uppercase mb-4 text-cyan flex items-center gap-2">
          <i data-lucide="bar-chart-3" style="width:16px;height:16px;"></i> ${t('insights.density_title')}
        </h4>
        <div class="chart-container" style="height:150px;margin-bottom:16px;">
          <canvas id="chart-density"></canvas>
        </div>
        <p class="mono-xs text-muted">${t('insights.density_desc')}</p>
      </div>

      <!-- DS Insights: Fraîcheur & Corrélations Cross-Secteurs -->
      <div id="ds-insights-section" class="mb-6"></div>

      <!-- Reports Library Collapsible Card Container -->
      <div class="card mb-6" style="border-color:var(--border-strong);overflow:hidden;" id="reports-library-card">
        <div class="flex justify-between items-center" style="padding:14px 16px;background:var(--bg-alt);cursor:pointer;user-select:none;" id="toggle-reports-library">
          <h4 class="uppercase mono-sm flex items-center gap-2" style="margin:0;">
            <i data-lucide="library" style="width:16px;height:16px;" class="text-cyan"></i>
            ${t('insights.library_title')}
            <span class="badge badge--valid mono-xs" id="reports-library-count-badge" style="margin-left:6px;font-weight:600;">0</span>
          </h4>
          <div class="flex items-center gap-2">
            <span class="mono-xs text-muted" id="reports-library-toggle-hint">${t('common.open')}</span>
            <i data-lucide="chevron-down" id="reports-library-chevron" style="width:16px;height:16px;transition:transform .2s;"></i>
          </div>
        </div>

        <div id="reports-library-wrapper" style="padding:16px;display:block;">
          <div id="reports-library-list" class="flex flex-col gap-2 reports-library-scroll"></div>
        </div>
      </div>

      <h4 class="uppercase mb-4 flex items-center gap-2" style="font-size:14px;">
        <i data-lucide="sparkles" style="width:16px;height:16px;" class="text-accent"></i> ${t('insights.studies_title')}
      </h4>

      <div id="new-study-container" class="mb-6">
        <div class="card" style="padding:20px;text-align:center;">
          <p class="mono-sm text-muted mb-3">${t('insights.placeholder')}</p>
        </div>
      </div>

      <button class="btn btn-primary w-full justify-center mono-md fw-700" id="btn-run-analysis" style="padding:14px;">
        <i data-lucide="sparkles" style="width:18px;height:18px;"></i> ${t('insights.btn_run')}
      </button>
    `;
  },

  async init() {
    if (window.lucide) window.lucide.createIcons();

    // 1. Load all sections in parallel
    await Promise.all([
      updateInsightsDensityChart(activeInsightSector),
      loadReportsLibrary(activeInsightSector),
      loadCrossSectorInsights(),
    ]);

    // Wire up Reports Library collapsible toggle
    const toggleLibrary = document.getElementById('toggle-reports-library');
    const libraryWrapper = document.getElementById('reports-library-wrapper');
    const libraryChevron = document.getElementById('reports-library-chevron');
    const libraryHint = document.getElementById('reports-library-toggle-hint');

    if (toggleLibrary && libraryWrapper) {
      toggleLibrary.addEventListener('click', () => {
        const isHidden = libraryWrapper.style.display === 'none';
        libraryWrapper.style.display = isHidden ? 'block' : 'none';
        if (libraryChevron) {
          libraryChevron.style.transform = isHidden ? '' : 'rotate(-90deg)';
        }
        if (libraryHint) {
          libraryHint.textContent = isHidden ? t('common.open') : t('common.close');
        }
      });
    }
    // 2. Sector Tab Buttons -> Dynamically filter density chart, library, and active sector state
    document.querySelectorAll('.insights-tab-btn').forEach(btn => {
      btn.addEventListener('click', async (e) => {
        const sec = e.currentTarget.getAttribute('data-sector');
        activeInsightSector = sec;

        document.querySelectorAll('.insights-tab-btn').forEach(b => {
          b.classList.remove('btn-cyan');
          b.classList.add('btn-ghost');
        });
        e.currentTarget.classList.remove('btn-ghost');
        e.currentTarget.classList.add('btn-cyan');

        await updateInsightsDensityChart(sec);
        await loadReportsLibrary(sec);
      });
    });

    // 3. RUN NEW ANALYSIS Button (Calls FastAPI POST /api/v1/studies)
    const runBtn = document.getElementById('btn-run-analysis');
    if (runBtn) {
      runBtn.addEventListener('click', async () => {
        const studyContainer = document.getElementById('new-study-container');
        const statusTag = document.getElementById('agent-status-tag');

        runBtn.disabled = true;
        runBtn.innerHTML = `<i data-lucide="loader" class="animate-spin" style="width:18px;height:18px;"></i> ${t('insights.btn_run_loading')}`;
        if (window.lucide) window.lucide.createIcons();

        if (statusTag) {
          statusTag.innerHTML = `<i data-lucide="cpu" style="width:14px;height:14px;"></i> ${t('insights.status_thinking')}`;
          if (window.lucide) window.lucide.createIcons();
        }

        if (studyContainer) {
          studyContainer.innerHTML = `
            <div class="card card--accent-border" style="padding:20px;text-align:center;">
              <p class="mono-sm text-cyan mb-2 flex items-center justify-center gap-2">
                <i data-lucide="zap" style="width:16px;height:16px;"></i> ${t('insights.running_msg')} "${activeInsightSector.toUpperCase()}"...
              </p>
              <p class="mono-xs text-muted">Synthèse statistique des observations et rédaction du rapport...</p>
            </div>
          `;
          if (window.lucide) window.lucide.createIcons();
        }

        try {
          const targetSector = activeInsightSector === 'all' ? null : activeInsightSector;
          const result = await generateStudy(targetSector);

          if (statusTag) {
            statusTag.innerHTML = `<i data-lucide="check-circle" style="width:14px;height:14px;"></i> ${t('insights.status_done')}`;
            if (window.lucide) window.lucide.createIcons();
          }

          runBtn.disabled = false;
          runBtn.innerHTML = `<i data-lucide="sparkles" style="width:18px;height:18px;"></i> ${t('insights.btn_run_new')}`;
          if (window.lucide) window.lucide.createIcons();

          if (result && studyContainer) {
            studyContainer.innerHTML = renderReportBlock(result);
            if (window.lucide) window.lucide.createIcons();
          }

          // Refresh the library so the new report appears immediately, marked fresh.
          await loadReportsLibrary(activeInsightSector);
        } catch (err) {
          console.error('Study generation error:', err);
          if (statusTag) {
            statusTag.innerHTML = `<i data-lucide="check-circle-2" style="width:14px;height:14px;"></i> ${t('insights.status_active')}`;
            if (window.lucide) window.lucide.createIcons();
          }
          runBtn.disabled = false;
          runBtn.innerHTML = `<i data-lucide="sparkles" style="width:18px;height:18px;"></i> ${t('insights.btn_run')}`;
          if (window.lucide) window.lucide.createIcons();

          if (studyContainer) {
            studyContainer.innerHTML = `
              <div class="card" style="padding:16px;border-color:var(--red);">
                <p class="mono-sm text-accent mb-1 flex items-center gap-1"><i data-lucide="alert-triangle" style="width:16px;height:16px;"></i> ${t('insights.err_msg')}: ${escapeHtml(err.message)}</p>
                <p class="mono-xs text-muted">${t('insights.err_hint')}</p>
              </div>
            `;
            if (window.lucide) window.lucide.createIcons();
          }
        }
      });
    }
  }
};
