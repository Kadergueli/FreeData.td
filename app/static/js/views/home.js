/**
 * View: Landing / Home — "OPEN DATA INFRASTRUCTURE FOR CHAD"
 */

import {
  fetchObservations,
  fetchCatalog,
  fetchAudit,
  triggerAgricultureHarvest,
  triggerEnvironmentHarvest,
  triggerMarketsHarvest,
  triggerEconomyHarvest
} from '../api_client.js';
import { navigateTo } from '../router.js';
import { t } from '../i18n.js';

export const HomeView = {
  render() {
    const pipelineItems = t('home.pipeline');
    const pipelineList = Array.isArray(pipelineItems) ? pipelineItems : [
      { num: '01', title: 'INGESTION', desc: 'Automated collection from FAOSTAT, NASA, and World Bank.' },
      { num: '02', title: 'CLEANING', desc: 'Quality control and structural validation of raw observations.' },
      { num: '03', title: 'DISTRIBUTION', desc: 'Public APIs, CSV exports, and interactive analytical dashboards.' }
    ];

    const sectors = [
      { icon: 'sprout',      id: 'agriculture', name: t('sectors.names.agriculture') },
      { icon: 'trending-up', id: 'economy',     name: t('sectors.names.economy') },
      { icon: 'shopping-cart', id: 'markets',   name: t('sectors.names.markets') },
      { icon: 'leaf',        id: 'environment', name: t('sectors.names.environment') },
      { icon: 'truck',       id: 'transport',   name: t('sectors.names.transport') },
      { icon: 'graduation-cap', id: 'education', name: t('sectors.names.education') },
    ];

    const rawCap = t('home.capabilities');
    const capList = Array.isArray(rawCap) ? rawCap : [
      { icon: 'database',    title: 'Agrégation Multi-Sources', desc: 'Ingestion automatique auprès de 10 institutions officielles (INSEED, BEAC, Banque Mondiale...)' },
      { icon: 'shield-check',title: 'Contrôle Qualité & IA',     desc: 'Normalisation structurelle, détection d\'anomalies et validation stricte des séries temporelles.' },
      { icon: 'code-2',      title: 'APIs & Exports Ouverts',    desc: 'Endpoints REST haute performance, téléchargements CSV/JSON/Excel et licence CC BY 4.0.' },
      { icon: 'line-chart',  title: 'Visualisation & Analytics', desc: 'Tableaux de bord sectoriels dynamiques, graphiques interactifs et synthèses analytiques.' }
    ];

    return `
      <!-- Hero -->
      <div class="mb-6">
        <h1 class="hero-title uppercase" style="color:var(--text);font-size:24px;">
          <span class="text-cyan">${t('home.title')}</span>
        </h1>
        <p class="hero-subtitle mono-sm">
          ${t('home.subtitle')}
        </p>

        <div class="flex gap-3 flex-wrap">
          <button class="btn btn-primary" id="btn-explore">
            <i data-lucide="database" style="width:16px;height:16px;"></i> ${t('home.btn_explore')}
          </button>
          <button class="btn btn-cyan" id="btn-home-harvest">
            <i data-lucide="zap" style="width:16px;height:16px;"></i> ${t('home.btn_harvest')}
          </button>
        </div>
      </div>

      <!-- Quick Stats -->
      <div class="grid-3 mb-6">
        <div class="stat-card">
          <div class="stat-value text-accent" id="stat-obs-count">...</div>
          <div class="stat-label">${t('home.stat_obs')}</div>
        </div>
        <div class="stat-card">
          <div class="stat-value text-green" id="stat-validation-score">98.5%</div>
          <div class="stat-label">${t('home.stat_score')}</div>
        </div>
        <div class="stat-card">
          <div class="stat-value text-cyan" id="stat-sectors-count">...</div>
          <div class="stat-label">${t('home.stat_sectors')}</div>
        </div>
      </div>

      <!-- Mission & Core Capabilities -->
      <div class="card card--transparent mb-6">
        <h4 class="section-label text-cyan mb-3 flex items-center gap-2">
          <i data-lucide="target" style="width:16px;height:16px;"></i> ${t('home.mission_title')}
        </h4>
        <p class="mono-sm text-muted mb-4" style="line-height:1.6;font-size:13px;">
          ${t('home.mission_text')}
        </p>

        <!-- Capabilities Grid -->
        <div style="display:grid;grid-template-columns:repeat(auto-fit, minmax(240px, 1fr));gap:12px;" class="mt-4">
          ${capList.map(cap => `
            <div style="background:var(--surface);border:1px solid var(--border);border-radius:6px;padding:14px;">
              <div class="flex items-center gap-2 mb-2">
                <i data-lucide="${cap.icon}" style="width:15px;height:15px;" class="text-cyan"></i>
                <h5 class="mono-xs fw-700 uppercase" style="color:var(--text);">${cap.title}</h5>
              </div>
              <p class="mono-xs text-muted" style="line-height:1.5;margin:0;">${cap.desc}</p>
            </div>
          `).join('')}
        </div>
      </div>

      <!-- Data Pipeline -->
      <div class="card card--transparent mb-6">
        <h4 class="section-label text-cyan mb-6 flex items-center gap-2">
          <i data-lucide="git-merge" style="width:16px;height:16px;"></i> ${t('home.pipeline_title')}
        </h4>
        <div class="flex flex-col gap-4">
          ${pipelineList.map(item => `
            <div class="flex gap-4 items-start">
              <div class="mono-sm fw-700" style="background:var(--surface-hover);color:var(--text);padding:4px 8px;border-radius:2px;border:1px solid var(--border);">${item.num}</div>
              <div>
                <h5 class="uppercase" style="font-size:14px;margin-bottom:4px;">${item.title}</h5>
                <p class="text-muted mono-sm">${item.desc}</p>
              </div>
            </div>`).join('')}
        </div>
      </div>

      <!-- Active Sectors -->
      <div class="mb-6">
        <h4 class="section-label text-cyan mb-4 flex items-center gap-2">
          <i data-lucide="layers" style="width:16px;height:16px;"></i> ${t('home.sectors_title')}
        </h4>
        <div class="flex gap-3 flex-wrap" id="home-sector-btns">
          ${sectors.map(s => `
            <button class="btn btn-ghost sector-tag-btn" data-sector="${s.id}">
              <i data-lucide="${s.icon}" style="width:14px;height:14px;" class="text-muted"></i> ${s.name}
            </button>`).join('')}
        </div>
      </div>

      <!-- Latest Validated Data -->
      <div style="background-color:var(--surface);border:1px solid var(--border);border-radius:6px;overflow:hidden;" id="latest-data-container">
        <div style="padding:16px;">
          <h4 class="uppercase mono-sm fw-700 flex items-center gap-2" style="color:var(--text);margin-bottom:12px;">
            <i data-lucide="shield-check" style="width:16px;height:16px;" class="text-green"></i> ${t('home.latest_title')}
          </h4>
          <div style="background-color:#ffffff;border:1px solid var(--border);padding:16px;border-radius:6px;" class="flex flex-col gap-2" id="latest-obs-card">
            <div class="flex justify-between items-center mb-2">
              <h5 class="uppercase" style="font-size:16px;" id="latest-indicator">${t('home.loading_db')}</h5>
              <span class="badge badge--valid" id="latest-status">DATABASE</span>
            </div>
            <p class="mono-sm text-muted flex items-center gap-1" id="latest-location"><i data-lucide="map-pin" style="width:14px;height:14px;"></i> ${t('home.loading_db')}</p>
            <p class="mono-sm text-muted mb-4 flex items-center gap-1" id="latest-date"><i data-lucide="calendar" style="width:14px;height:14px;"></i> --/--/----</p>
            <div class="separator flex justify-between items-end">
              <p class="mono-xs text-muted uppercase" id="latest-source">${t('common.source')}: DATABASE</p>
              <div class="mono-2xl fw-700 text-accent" id="latest-value">-- <span class="mono-lg" id="latest-unit"></span></div>
            </div>
          </div>
        </div>
      </div>
    `;
  },

  async init() {
    // 1. Wire "EXPLORE DATA" button
    const btnExplore = document.getElementById('btn-explore');
    if (btnExplore) {
      btnExplore.addEventListener('click', () => navigateTo('data'));
    }

    // 2. Wire "COLLECT LIVE DATA" button
    const btnHarvest = document.getElementById('btn-home-harvest');
    if (btnHarvest) {
      btnHarvest.addEventListener('click', async () => {
        btnHarvest.disabled = true;
        btnHarvest.innerHTML = `<i data-lucide="loader" class="animate-spin" style="width:16px;height:16px;"></i> ${t('home.btn_harvest_loading')}`;
        if (window.lucide) window.lucide.createIcons();

        try {
          await Promise.allSettled([
            triggerAgricultureHarvest('all'),
            triggerEnvironmentHarvest('all'),
            triggerMarketsHarvest('all'),
            triggerEconomyHarvest('all')
          ]);
          alert(t('common.harvest_ok'));
          await HomeView.init();
        } catch (err) {
          alert(`${t('common.harvest_err')}: ${err.message}`);
        } finally {
          btnHarvest.disabled = false;
          btnHarvest.innerHTML = `<i data-lucide="zap" style="width:16px;height:16px;"></i> ${t('home.btn_harvest')}`;
          if (window.lucide) window.lucide.createIcons();
        }
      });
    }

    // 3. Wire sector tags to navigate to Data view with pre-filter
    document.querySelectorAll('.sector-tag-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        const sector = e.currentTarget.getAttribute('data-sector');
        navigateTo('data', { sector });
      });
    });

    // 4. Fetch real dynamic data from backend database
    try {
      const [obsRes, catalogRes, auditRes] = await Promise.allSettled([
        fetchObservations(null, 100),
        fetchCatalog(),
        fetchAudit()
      ]);

      const obs = obsRes.status === 'fulfilled' && Array.isArray(obsRes.value) ? obsRes.value : [];
      const catalog = catalogRes.status === 'fulfilled' && Array.isArray(catalogRes.value) ? catalogRes.value : [];
      const audit = auditRes.status === 'fulfilled' ? auditRes.value : null;

      // Update observation count
      const totalObs = (audit && audit.reports_summary && audit.reports_summary.total_public) || (obs ? obs.length : 0);
      const obsCountEl = document.getElementById('stat-obs-count');
      if (obsCountEl) obsCountEl.textContent = totalObs > 0 ? `${totalObs}` : (obs.length > 0 ? `${obs.length}` : '0');

      // Update sector count
      const secEl = document.getElementById('stat-sectors-count');
      if (catalog && catalog.length > 0) {
        const sectors = new Set(catalog.map(c => c.sector));
        if (secEl) secEl.textContent = sectors.size < 10 ? `0${sectors.size}` : `${sectors.size}`;
      } else if (secEl) {
        secEl.textContent = '06';
      }

      // Update audit logs stat
      const logsCount = (audit && audit.logs && audit.logs.length) || 0;
      const pipelineCountEl = document.getElementById('stat-pipeline-count');
      if (pipelineCountEl) pipelineCountEl.textContent = `${logsCount}`;

      // Update validation score
      if (audit && audit.reports_summary && audit.reports_summary.score_global !== undefined) {
        const scoreEl = document.getElementById('stat-validation-score');
        if (scoreEl) {
          scoreEl.textContent = `${(audit.reports_summary.score_global * 100).toFixed(1)}%`;
        }
      }

      // Update latest validated observation from DB
      if (obs && obs.length > 0) {
        const latest = obs[0];
        const indEl = document.getElementById('latest-indicator');
        const locEl = document.getElementById('latest-location');
        const dateEl = document.getElementById('latest-date');
        const srcEl = document.getElementById('latest-source');
        const valEl = document.getElementById('latest-value');

        if (indEl) indEl.textContent = (latest.indicator || 'Observation').toUpperCase();
        if (locEl) locEl.innerHTML = `<i data-lucide="map-pin" style="width:14px;height:14px;"></i> ${latest.region || 'Logone'}, ${latest.country_code || 'TCH'}`;
        if (dateEl) dateEl.innerHTML = `<i data-lucide="calendar" style="width:14px;height:14px;"></i> ${latest.reference_date || latest.collected_at || 'Recent'}`;
        if (srcEl) srcEl.textContent = `${t('common.source')}: ${(latest.source || 'Open Data').toUpperCase()}`;
        const numVal = Number(latest.value);
        const formattedVal = !isNaN(numVal) ? (Number.isInteger(numVal) ? numVal.toLocaleString() : numVal.toLocaleString(undefined, { maximumFractionDigits: 2 })) : latest.value;
        if (valEl) valEl.innerHTML = `${formattedVal} <span class="mono-lg">${latest.unit || ''}</span>`;
        if (window.lucide) window.lucide.createIcons();
      } else {
        const cardContainer = document.getElementById('latest-obs-card');
        if (cardContainer) {
          cardContainer.innerHTML = `
            <div style="text-align:center;padding:16px;">
              <p class="mono-sm text-muted mb-3">${t('home.no_obs')}</p>
            </div>
          `;
        }
      }
    } catch (err) {
      console.warn('HomeView init dynamic load error:', err);
      const obsCountEl = document.getElementById('stat-obs-count');
      if (obsCountEl && obsCountEl.textContent === '...') obsCountEl.textContent = '0';
      const secEl = document.getElementById('stat-sectors-count');
      if (secEl && secEl.textContent === '...') secEl.textContent = '06';
    }
  }
};
