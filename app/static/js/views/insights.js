/**
 * View: AI Insights — Automated Exploration & Trend Analysis (DATABASE & LLM DIRECT)
 */

import { generateStudy, fetchObservations, fetchStudies } from '../api_client.js';
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

/** Renders the full report block — shared by "just generated" and "opened from
 * the library" code paths. All fields are escaped: they come from the LLM and/or
 * harvested external data, never trusted as HTML. */
function renderReportBlock(result) {
  const reportText = escapeHtml(result.report || '');
  const modelName = escapeHtml(result.model || 'N/A');
  const sectorLabel = escapeHtml((result.sector || t('insights.sectors.all')).toUpperCase());
  const obsCount = escapeHtml(result.observations_used ?? 'N/A');
  const dateLabel = escapeHtml(formatStudyDate(result.created_at));
  return `
    <div class="card card--accent-border mb-4" style="padding:20px;">
      <div class="flex justify-between items-center mb-3">
        <span class="badge badge--valid">${t('insights.result_badge')}</span>
        <span class="mono-xs text-green">${t('insights.result_model')}: ${modelName}</span>
      </div>
      <h4 class="mono-lg mb-2">${t('insights.result_title')} (${sectorLabel})</h4>
      <p class="mono-xs text-muted mb-4">${t('insights.result_obs')}: ${obsCount} · ${dateLabel}</p>
      <div class="mono-sm" style="background:var(--surface);padding:16px;border:1px solid var(--border);border-radius:6px;white-space:pre-wrap;max-height:400px;overflow-y:auto;line-height:1.6;color:var(--text);">${reportText}</div>
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
  if (!listEl) return;
  listEl.innerHTML = `<p class="mono-xs text-muted flex items-center gap-2"><i data-lucide="loader" class="animate-spin" style="width:14px;height:14px;"></i> ${t('common.loading')}</p>`;
  if (window.lucide) window.lucide.createIcons();

  const targetSector = sector === 'all' ? null : sector;
  const studies = await fetchStudies(targetSector, 10);

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

      <!-- Reports Library — free to browse, no LLM call, always available even to
           visitors who never click "generate" -->
      <h4 class="uppercase mb-4 flex items-center gap-2" style="font-size:14px;">
        <i data-lucide="library" style="width:16px;height:16px;" class="text-cyan"></i> ${t('insights.library_title')}
      </h4>
      <div id="reports-library-list" class="flex flex-col gap-2 mb-6"></div>

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

    // 1. Initialise density chart + reports library for the current sector
    await updateInsightsDensityChart(activeInsightSector);
    await loadReportsLibrary(activeInsightSector);

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
