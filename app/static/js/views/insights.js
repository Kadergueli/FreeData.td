/**
 * View: AI Insights — Automated Exploration & Trend Analysis (DATABASE & LLM DIRECT)
 */

import { generateStudy, fetchObservations } from '../api_client.js';
import { initChartDensity } from '../charts.js';
import { t } from '../i18n.js';

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

      <div style="border-top:1px solid var(--border);border-bottom:1px solid var(--border);padding:12px 0;" class="flex gap-2 mb-6" id="insights-sector-tabs">
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

    // 1. Initialise density chart dynamically for current sector
    await updateInsightsDensityChart(activeInsightSector);

    // 2. Sector Tab Buttons -> Dynamically filter density chart and active sector state
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

        // Dynamically update the Density Chart for this sector
        await updateInsightsDensityChart(sec);
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
            const reportText = result.report || JSON.stringify(result, null, 2);
            studyContainer.innerHTML = `
              <div class="card card--accent-border mb-4" style="padding:20px;">
                <div class="flex justify-between items-center mb-3">
                  <span class="badge badge--valid">${t('insights.result_badge')}</span>
                  <span class="mono-xs text-green">${t('insights.result_model')}: ${result.model || 'Gemini'}</span>
                </div>
                <h4 class="mono-lg mb-2">${t('insights.result_title')} (${(result.sector || t('insights.sectors.all')).toUpperCase()})</h4>
                <p class="mono-xs text-muted mb-4">${t('insights.result_obs')}: ${result.observations_used || 'N/A'}</p>
                <div class="mono-sm" style="background:var(--surface);padding:16px;border:1px solid var(--border);border-radius:6px;white-space:pre-wrap;max-height:400px;overflow-y:auto;line-height:1.6;color:var(--text);">${reportText}</div>
              </div>
            `;
          }
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
                <p class="mono-sm text-accent mb-1 flex items-center gap-1"><i data-lucide="alert-triangle" style="width:16px;height:16px;"></i> ${t('insights.err_msg')}: ${err.message}</p>
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
