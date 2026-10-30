/**
 * View: Landing / Home — "OPEN DATA INFRASTRUCTURE FOR CHAD"
 */

import { fetchObservations, fetchStats, fetchAudit } from '../api_client.js';
import { formatDate, formatScore } from '../ui.js';
import { navigateTo } from '../router.js';
import { t, getLang } from '../i18n.js';
import { OFFICIAL_SOURCES } from '../sources_catalog.js';
import { escapeHtml } from '../sanitize.js';

const ALL_SECTOR_COUNT = 9;


export const HomeView = {
  render() {
    const pipelineItems = t('home.pipeline');
    const pipelineList = Array.isArray(pipelineItems) ? pipelineItems : [
      { num: '01', title: 'INGESTION', desc: 'Automated collection from FAOSTAT, NASA, and World Bank.' },
      { num: '02', title: 'CLEANING', desc: 'Quality control and structural validation of raw observations.' },
      { num: '03', title: 'DISTRIBUTION', desc: 'Public APIs, CSV exports, and interactive analytical dashboards.' }
    ];

    const sectors = [
      { icon: 'sprout',         id: 'agriculture', name: t('sectors.names.agriculture') },
      { icon: 'trending-up',    id: 'economy',     name: t('sectors.names.economy') },
      { icon: 'shopping-cart',  id: 'markets',     name: t('sectors.names.markets') },
      { icon: 'leaf',           id: 'environment', name: t('sectors.names.environment') },
      { icon: 'heart-pulse',    id: 'health',      name: t('sectors.names.health') },
      { icon: 'zap',            id: 'energy',      name: t('sectors.names.energy') },
      { icon: 'truck',          id: 'transport',   name: t('sectors.names.transport') },
      { icon: 'graduation-cap', id: 'education',   name: t('sectors.names.education') },
      { icon: 'users',          id: 'demography',  name: t('sectors.names.demography') },
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
        </div>
      </div>

      <!-- Sources (accordion — closed by default so it costs no space on phones) -->
      <div class="card card--transparent mb-6 accordion-section" data-accordion="sources">
        <button type="button" class="accordion-trigger" data-accordion-trigger="sources" aria-expanded="false" aria-controls="acc-panel-sources">
          <div class="flex items-center gap-2">
            <i data-lucide="database" style="width:16px;height:16px;" class="text-cyan"></i>
            <div>
              <div class="accordion-title">${t('home.sources_strip_title')}</div>
              <div class="accordion-teaser">${t('home.sources_strip_teaser').replace('{n}', String(OFFICIAL_SOURCES.length))}</div>
            </div>
          </div>
          <i data-lucide="chevron-down" style="width:18px;height:18px;" class="accordion-chevron"></i>
        </button>
        <div class="accordion-panel" id="acc-panel-sources" role="region"><div><div class="accordion-panel-inner">
          <div class="flex gap-2 flex-wrap">
            ${OFFICIAL_SOURCES.map(s => `<span class="sources-strip__chip">${escapeHtml(s.name)}</span>`).join('')}
          </div>
        </div></div></div>
      </div>

      <!-- Quick Stats -->
      <div class="stat-row mb-6">
        <div class="stat-card">
          <div class="stat-value text-accent" id="stat-obs-count"><span class="skeleton"></span></div>
          <div class="stat-label">${t('home.stat_obs')}</div>
        </div>
        <div class="stat-card">
          <div class="stat-value text-green" id="stat-validation-score"><span class="skeleton"></span></div>
          <div class="stat-label">${t('home.stat_score')}</div>
        </div>
        <div class="stat-card">
          <div class="stat-value text-cyan" id="stat-sectors-count"><span class="skeleton"></span></div>
          <div class="stat-label">${t('home.stat_sectors')}</div>
        </div>
      </div>

      <p class="mono-xs text-muted mb-6" id="home-last-update" aria-live="polite"></p>

      <!-- Mission & Core Capabilities (accordion — opens on demand) -->
      <div class="card card--transparent mb-6 accordion-section" data-accordion="mission">
        <button type="button" class="accordion-trigger" data-accordion-trigger="mission" aria-expanded="false" aria-controls="acc-panel-mission">
          <div class="flex items-center gap-2">
            <i data-lucide="target" style="width:16px;height:16px;" class="text-cyan"></i>
            <div>
              <div class="accordion-title">${t('home.mission_title')}</div>
              <div class="accordion-teaser">${t('home.mission_teaser')}</div>
            </div>
          </div>
          <i data-lucide="chevron-down" style="width:18px;height:18px;" class="accordion-chevron"></i>
        </button>
        <div class="accordion-panel" id="acc-panel-mission" role="region"><div><div class="accordion-panel-inner">
          <p class="body-text mb-4">${t('home.mission_text')}</p>
          <div style="display:grid;grid-template-columns:repeat(auto-fit, minmax(240px, 1fr));gap:12px;">
            ${capList.map(cap => `
              <div style="background:var(--surface);border:1px solid var(--border);border-radius:6px;padding:14px;">
                <div class="flex items-center gap-2 mb-2">
                  <i data-lucide="${cap.icon}" style="width:15px;height:15px;" class="text-cyan"></i>
                  <h5 class="fw-700" style="font-family:var(--font-sans);font-size:13px;color:var(--text);">${cap.title}</h5>
                </div>
                <p class="body-text" style="font-size:13px;margin:0;">${cap.desc}</p>
              </div>
            `).join('')}
          </div>
        </div></div></div>
      </div>

      <!-- Data Pipeline (accordion — opens on demand) -->
      <div class="card card--transparent mb-6 accordion-section" data-accordion="pipeline">
        <button type="button" class="accordion-trigger" data-accordion-trigger="pipeline" aria-expanded="false" aria-controls="acc-panel-pipeline">
          <div class="flex items-center gap-2">
            <i data-lucide="git-merge" style="width:16px;height:16px;" class="text-cyan"></i>
            <div>
              <div class="accordion-title">${t('home.pipeline_title')}</div>
              <div class="accordion-teaser">${t('home.pipeline_teaser')}</div>
            </div>
          </div>
          <i data-lucide="chevron-down" style="width:18px;height:18px;" class="accordion-chevron"></i>
        </button>
        <div class="accordion-panel" id="acc-panel-pipeline" role="region"><div><div class="accordion-panel-inner">
          <div class="pipeline-grid">
            ${pipelineList.map(item => `
              <div class="flex gap-4 items-start">
                <div class="mono-sm fw-700" style="background:var(--surface-hover);color:var(--text);padding:4px 8px;border-radius:2px;border:1px solid var(--border);">${item.num}</div>
                <div>
                  <h5 style="font-family:var(--font-sans);font-size:14px;margin-bottom:4px;">${item.title}</h5>
                  <p class="body-text">${item.desc}</p>
                </div>
              </div>`).join('')}
          </div>
        </div></div></div>
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
              <span class="badge badge--valid" id="latest-status">${t('common.validated')}</span>
            </div>
            <p class="mono-sm text-muted flex items-center gap-1" id="latest-location"><i data-lucide="map-pin" style="width:14px;height:14px;"></i> ${t('home.loading_db')}</p>
            <p class="mono-sm text-muted mb-4 flex items-center gap-1" id="latest-date"><i data-lucide="calendar" style="width:14px;height:14px;"></i> --/--/----</p>
            <div class="separator" style="display:flex;flex-direction:column;gap:6px;">
              <div class="mono-2xl fw-700 text-accent" id="latest-value" style="word-break:break-word;">-- <span class="mono-lg" id="latest-unit"></span></div>
              <p class="mono-xs text-muted uppercase" id="latest-source">${t('common.source')}: —</p>
            </div>
          </div>
        </div>
      </div>
    `;
  },

  /** Called by the router once per render. Listeners are bound HERE, exactly once
   *  per render; data (re)loading lives in loadData() so it can be re-run without
   *  stacking duplicate listeners. */
  async init() {
    document.getElementById('btn-explore')?.addEventListener('click', () => navigateTo('data'));

    document.querySelectorAll('[data-accordion-trigger]').forEach(trigger => {
      trigger.addEventListener('click', () => {
        const section = trigger.closest('.accordion-section');
        if (!section) return;
        const isOpen = section.classList.toggle('is-open');
        trigger.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
      });
    });

    document.querySelectorAll('.sector-tag-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        navigateTo('data', { sector: e.currentTarget.getAttribute('data-sector') });
      });
    });

    await HomeView.loadData();
  },

  async loadData() {
    // 3 light calls: real totals, the single latest row, the validation score.
    const [statsRes, latestRes, auditRes] = await Promise.allSettled([
      fetchStats(),
      fetchObservations(null, 1),
      fetchAudit(),
    ]);
    const stats = statsRes.status === 'fulfilled' ? statsRes.value : null;
    const latestRows = latestRes.status === 'fulfilled' && Array.isArray(latestRes.value) ? latestRes.value : [];
    const audit = auditRes.status === 'fulfilled' ? auditRes.value : null;

    // Observations — real total, or an honest dash when unknown (never a made-up number).
    const obsEl = document.getElementById('stat-obs-count');
    if (obsEl) obsEl.textContent = stats ? Number(stats.total || 0).toLocaleString() : '—';

    // Sectors that actually hold data, out of the 8 the platform covers.
    const secEl = document.getElementById('stat-sectors-count');
    if (secEl) {
      if (stats && stats.sectors) {
        const withData = Object.values(stats.sectors).filter(c => c > 0).length;
        secEl.textContent = `${String(withData).padStart(2, '0')} / ${String(ALL_SECTOR_COUNT).padStart(2, '0')}`;
      } else {
        secEl.textContent = '—';
      }
    }

    // Validation score — only shown when the audit actually returned one.
    const scoreEl = document.getElementById('stat-validation-score');
    if (scoreEl) {
      scoreEl.textContent = formatScore(audit);
    }

    const updEl = document.getElementById('home-last-update');
    if (updEl) {
      const d = stats && stats.last_update ? formatDate(stats.last_update, getLang()) : '';
      updEl.textContent = d ? `${t('home.last_update')} : ${d}` : '';
    }

    // Latest observation card.
    if (latestRows.length > 0) {
      const latest = latestRows[0];
      const set = (id, html) => { const el = document.getElementById(id); if (el) el.innerHTML = html; };
      set('latest-indicator', escapeHtml((latest.indicator || '—').toUpperCase()));
      set('latest-location', `<i data-lucide="map-pin" style="width:14px;height:14px;"></i> ${escapeHtml([latest.region, latest.country_code].filter(Boolean).join(', ') || '—')}`);
      set('latest-date', `<i data-lucide="calendar" style="width:14px;height:14px;"></i> ${escapeHtml(formatDate(latest.reference_date || latest.collected_at, getLang()) || '—')}`);
      set('latest-source', `${t('common.source')}: ${escapeHtml((latest.source || '—').toUpperCase())}`);
      const num = Number(latest.value);
      const valueText = latest.value === null || latest.value === undefined || isNaN(num)
        ? '—'
        : num.toLocaleString(undefined, { maximumFractionDigits: 2 });
      set('latest-value', `${valueText} <span class="mono-lg" style="display:inline;">${escapeHtml(latest.unit || '')}</span>`);
      if (window.lucide) window.lucide.createIcons();
    } else {
      const card = document.getElementById('latest-obs-card');
      if (card) {
        card.innerHTML = `<div style="text-align:center;padding:16px;"><p class="mono-sm text-muted mb-3">${t('home.no_obs')}</p></div>`;
      }
    }
  }
};
