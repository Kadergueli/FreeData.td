/**
 * View: Data Explorer — Repository of open data.
 *
 * - Search runs on the SERVER (it used to filter only the ~15 rows already on screen).
 * - Missing values are shown as "—" (they used to render as "0").
 * - The trend chart plots ONE indicator in ONE region (it used to mix prices, rainfall…
 *   on a single line) and never draws invented data.
 * - Responses are sequenced: a slow, older request can no longer overwrite a newer one.
 */

import { fetchObservations, fetchStats } from '../api_client.js';
import { initChartMais } from '../charts.js';
import { formatDate } from '../ui.js';
import { t, getLang } from '../i18n.js';
import { escapeHtml } from '../sanitize.js';

const PAGE_SIZE = 15;
const SEARCH_DEBOUNCE_MS = 300;

function getSectorsFilter() {
  return [
    { id: 'tous', label: t('data.filter_all') },
    { id: 'agriculture', label: t('sectors.names.agriculture') },
    { id: 'environment', label: t('sectors.names.environment') },
    { id: 'markets', label: t('sectors.names.markets') },
    { id: 'health', label: t('sectors.names.health') },
    { id: 'energy', label: t('sectors.names.energy') },
    { id: 'transport', label: t('sectors.names.transport') },
    { id: 'education', label: t('sectors.names.education') },
    { id: 'economy', label: t('sectors.names.economy') },
    { id: 'demography', label: t('sectors.names.demography') },
  ];
}

// Per-visit state is reset on every render(); only display preferences persist.
let activeSector = 'tous';
let currentLimit = PAGE_SIZE;
let searchQuery = '';
let chartIndicator = '';
let currentObsData = [];
let totalKnown = null;
let sortAsc = false;
let isGridView = false;
let _reqId = 0;

function formatObsValue(val) {
  if (val === null || val === undefined || val === '') return '—';
  const num = Number(val);
  if (isNaN(num)) return escapeHtml(val);
  return num.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 2 });
}

function renderObservationCard(o) {
  // Every field can originate from a third-party source — never trust it as HTML.
  const badgeTextRaw = String(o.status || t('common.validated'));
  const isValid = ['validated', 'validé', 'valide'].includes(badgeTextRaw.toLowerCase())
    || badgeTextRaw === t('common.validated');
  const badgeClass = isValid ? 'badge--valid' : 'badge--cyan';
  const badgeText = escapeHtml(badgeTextRaw.toUpperCase());
  const sector = escapeHtml((o.sector || '').toUpperCase());
  const unit = escapeHtml(o.unit || '');
  const indicator = escapeHtml(o.indicator || '—');
  const region = escapeHtml(o.region || '—');
  const date = escapeHtml(formatDate(o.reference_date || o.collected_at, getLang()) || '—');
  const source = escapeHtml((o.source || '—').toUpperCase());
  const countryCode = escapeHtml(o.country_code || '');

  return `
    <div class="card obs-card-item" style="padding:16px;">
      <div class="flex justify-between items-start mb-2">
        <span class="badge ${badgeClass}">${badgeText}</span>
        <span class="mono-xs text-muted">${sector}</span>
      </div>
      <div class="mono-2xl fw-700 mb-2" style="color:var(--text);">${formatObsValue(o.value)} <span class="mono-lg" style="color:var(--text-muted);">${unit}</span></div>
      <p class="mono-sm flex items-center gap-1"><i data-lucide="map-pin" style="width:14px;height:14px;" class="text-accent"></i> ${indicator} — ${region}</p>
      <p class="mono-xs text-muted mb-4 flex items-center gap-1"><i data-lucide="calendar" style="width:12px;height:12px;"></i> ${date}</p>
      <div class="separator flex justify-between items-center pt-2">
        <span class="mono-xs text-muted">${t('common.source')}: ${source}</span>
        <span class="mono-xs text-muted">${countryCode}</span>
      </div>
    </div>`;
}

/** Pick the (indicator, region) series to chart: the chosen indicator, in the region that
 *  has the most points for it. Returns { rows, indicator, region, unit, indicators }. */
function pickSeries(rows) {
  const byInd = new Map();
  rows.forEach(r => {
    if (!r.indicator || r.value === null || r.value === undefined || isNaN(Number(r.value))) return;
    byInd.set(r.indicator, (byInd.get(r.indicator) || 0) + 1);
  });
  const indicators = [...byInd.entries()].sort((a, b) => b[1] - a[1]).map(([name]) => name);
  const indicator = indicators.includes(chartIndicator) ? chartIndicator : (indicators[0] || '');
  const ofInd = rows.filter(r => r.indicator === indicator);
  const byReg = new Map();
  ofInd.forEach(r => byReg.set(r.region || '', (byReg.get(r.region || '') || 0) + 1));
  const region = [...byReg.entries()].sort((a, b) => b[1] - a[1]).map(([name]) => name)[0] || '';
  const series = ofInd.filter(r => (r.region || '') === region);
  return { rows: series, indicator, region, unit: (series[0] && series[0].unit) || '', indicators };
}

export const DataView = {
  render(params = {}) {
    activeSector = (params.sector || 'tous').toLowerCase();
    currentLimit = PAGE_SIZE;
    searchQuery = '';
    chartIndicator = '';
    currentObsData = [];
    totalKnown = null;
    _reqId += 1; // invalidate anything still in flight from a previous visit

    return `
      <div class="flex justify-between items-start mb-4 flex-wrap gap-3">
        <h2 class="hero-title uppercase" style="font-size:20px;margin-bottom:0;">${t('data.title')}</h2>
      </div>

      <div class="flex gap-2 mb-6">
        <div style="flex:1;">
          <input class="input-search" type="search" placeholder="${t('data.search')}" id="search-obs" value="" aria-label="${t('data.search')}" maxlength="100">
        </div>
        <button class="btn btn-ghost" id="btn-grid-toggle" style="padding:0 16px;" title="${t('data.layout_toggle')}" aria-label="${t('data.layout_toggle')}" aria-pressed="${isGridView}">
          <i data-lucide="${isGridView ? 'list' : 'layout-grid'}" style="width:16px;height:16px;"></i>
        </button>
      </div>

      <div class="mb-6">
        <h4 class="mono-xs text-muted uppercase mb-2">${t('data.sectors_label')}</h4>
        <div class="flex gap-2 flex-wrap" id="sector-filter-buttons">
          ${getSectorsFilter().map(s => {
            const isActive = s.id === activeSector;
            return `<button type="button" class="btn ${isActive ? 'btn-cyan' : 'btn-ghost'} filter-sector-btn mono-sm" data-sector="${s.id}" aria-pressed="${isActive}">${s.label}</button>`;
          }).join('')}
        </div>
      </div>

      <div class="flex justify-between items-center mb-4">
        <h4 class="uppercase" style="font-size:14px;" id="obs-count-header" aria-live="polite">${t('data.obs_header')} (${t('common.loading')})</h4>
        <button type="button" class="mono-xs text-cyan flex items-center gap-1" id="btn-sort-toggle" style="background:none;border:0;cursor:pointer;">
          <i data-lucide="arrow-up-down" style="width:12px;height:12px;"></i> ${t('data.sort_label')} ${sortAsc ? '▲' : '▼'}
        </button>
      </div>

      <div id="obs-list-container" class="${isGridView ? 'grid-2 mb-4' : 'flex flex-col gap-3 mb-4'}">
        <div class="card" style="padding:24px;text-align:center;" id="obs-loading-indicator">
          <p class="mono-sm text-muted">${t('data.loading_db')}</p>
        </div>
      </div>

      <div class="card mt-4 mb-4" style="padding:16px;border-color:var(--border-strong);" id="chart-section-card">
        <div class="flex justify-between items-center flex-wrap gap-2 mb-2">
          <h4 class="mono-sm uppercase text-cyan flex items-center gap-2">
            <i data-lucide="line-chart" style="width:16px;height:16px;"></i> ${t('data.trend_title')}
          </h4>
          <select id="chart-indicator-select" class="input-search" style="width:auto;max-width:100%;padding:6px 10px;font-size:12px;" aria-label="${t('data.chart_indicator')}"></select>
        </div>
        <p class="mono-xs text-muted mb-4" id="chart-caption"></p>
        <div class="chart-container" style="height:160px;">
          <canvas id="chart-mais"></canvas>
        </div>
        <div class="separator flex justify-between items-center mt-4">
          <span class="mono-xs text-muted">${t('data.trend_footer')}</span>
          <span class="mono-sm text-accent">${t('data.live')}</span>
        </div>
      </div>

      <div class="mt-4 mb-6">
        <button class="btn btn-ghost w-full justify-center mono-sm" id="btn-load-more" style="padding:12px;display:none;">
          <i data-lucide="plus" style="width:16px;height:16px;"></i> ${t('data.load_more')}
        </button>
      </div>
    `;
  },

  async init() {
    document.querySelectorAll('.filter-sector-btn').forEach(btn => {
      btn.addEventListener('click', async (e) => {
        activeSector = e.currentTarget.getAttribute('data-sector');
        document.querySelectorAll('.filter-sector-btn').forEach(b => {
          const on = b === e.currentTarget;
          b.classList.toggle('btn-cyan', on);
          b.classList.toggle('btn-ghost', !on);
          b.setAttribute('aria-pressed', String(on));
        });
        currentLimit = PAGE_SIZE;
        chartIndicator = '';
        await DataView.loadDynamicData();
      });
    });

    // Server-side search, debounced.
    let timer = null;
    document.getElementById('search-obs')?.addEventListener('input', (e) => {
      searchQuery = e.target.value;
      clearTimeout(timer);
      timer = setTimeout(() => {
        currentLimit = PAGE_SIZE;
        DataView.loadDynamicData();
      }, SEARCH_DEBOUNCE_MS);
    });

    document.getElementById('btn-grid-toggle')?.addEventListener('click', (e) => {
      isGridView = !isGridView;
      const container = document.getElementById('obs-list-container');
      if (container) container.className = isGridView ? 'grid-2 mb-4' : 'flex flex-col gap-3 mb-4';
      const btn = e.currentTarget;
      btn.setAttribute('aria-pressed', String(isGridView));
      btn.innerHTML = `<i data-lucide="${isGridView ? 'list' : 'layout-grid'}" style="width:16px;height:16px;"></i>`;
      if (window.lucide) window.lucide.createIcons();
    });

    document.getElementById('btn-sort-toggle')?.addEventListener('click', (e) => {
      sortAsc = !sortAsc;
      e.currentTarget.innerHTML = `<i data-lucide="arrow-up-down" style="width:12px;height:12px;"></i> ${t('data.sort_label')} ${sortAsc ? '▲' : '▼'}`;
      if (window.lucide) window.lucide.createIcons();
      DataView.renderObsList();
    });

    document.getElementById('btn-load-more')?.addEventListener('click', async (e) => {
      currentLimit += 25;
      e.currentTarget.disabled = true;
      await DataView.loadDynamicData({ keepScroll: true });
    });

    document.getElementById('chart-indicator-select')?.addEventListener('change', (e) => {
      chartIndicator = e.target.value;
      DataView.renderChart();
    });

    await DataView.loadDynamicData();
  },

  async loadDynamicData({ keepScroll = false } = {}) {
    const myReq = ++_reqId;
    const y = window.scrollY;
    const q = searchQuery.trim();

    const [rows, stats] = await Promise.all([
      fetchObservations(activeSector, currentLimit, { q }),
      totalKnown === null ? fetchStats() : Promise.resolve(null),
    ]);
    if (myReq !== _reqId) return; // a newer request (or another page) superseded this one

    currentObsData = Array.isArray(rows) ? rows : [];
    if (stats) {
      totalKnown = { total: stats.total, sectors: stats.sectors || {} };
    }

    const moreBtn = document.getElementById('btn-load-more');
    if (moreBtn) {
      moreBtn.disabled = false;
      // Another page exists only if the server filled the whole page we asked for.
      moreBtn.style.display = currentObsData.length >= currentLimit ? '' : 'none';
    }

    DataView.renderObsList();
    DataView.renderChart();
    if (keepScroll) window.scrollTo({ top: y, behavior: 'auto' });
  },

  renderChart() {
    const sel = document.getElementById('chart-indicator-select');
    const caption = document.getElementById('chart-caption');
    const s = pickSeries(currentObsData);
    if (sel) {
      sel.innerHTML = s.indicators.map(name => `<option value="${escapeHtml(name)}"${name === s.indicator ? ' selected' : ''}>${escapeHtml(name)}</option>`).join('');
      sel.style.display = s.indicators.length > 1 ? '' : 'none';
    }
    if (caption) {
      caption.textContent = s.indicator
        ? [s.indicator, s.region, s.unit].filter(Boolean).join(' · ')
        : '';
    }
    initChartMais(s.rows);
  },

  renderObsList() {
    const container = document.getElementById('obs-list-container');
    const header = document.getElementById('obs-count-header');
    if (!container) return;

    const sorted = [...currentObsData].sort((a, b) => {
      const da = new Date(a.reference_date || a.collected_at || 0).getTime() || 0;
      const db = new Date(b.reference_date || b.collected_at || 0).getTime() || 0;
      return sortAsc ? da - db : db - da;
    });

    if (header) {
      let total = null;
      if (!searchQuery.trim() && totalKnown) {
        total = activeSector === 'tous' ? totalKnown.total : totalKnown.sectors[activeSector];
      }
      header.textContent = `${t('data.obs_header')} : ${sorted.length}${typeof total === 'number' ? ` / ${total.toLocaleString()}` : ''}`;
    }

    if (sorted.length === 0) {
      const searching = searchQuery.trim() !== '';
      container.innerHTML = `
        <div class="card mb-4" style="padding:24px;text-align:center;grid-column:1/-1;">
          <p class="mono-sm text-muted mb-3">${searching
            ? `${t('data.no_results')} « ${escapeHtml(searchQuery.trim())} ».`
            : `${t('data.empty_msg')} "${escapeHtml(activeSector.toUpperCase())}".`}</p>
          ${searching ? '' : `<p class="mono-xs text-muted">${t('data.empty_hint')}</p>`}
        </div>`;
      if (window.lucide) window.lucide.createIcons();
      return;
    }

    container.innerHTML = sorted.map(renderObservationCard).join('');
    if (window.lucide) window.lucide.createIcons();
  },
};
