/**
 * View: Data Explorer — Repository de Données Ouvertes
 */

import {
  fetchObservations,
  triggerAgricultureHarvest,
  triggerEnvironmentHarvest,
  triggerMarketsHarvest,
  triggerEconomyHarvest
} from '../api_client.js';
import { initChartMais } from '../charts.js';
import { t } from '../i18n.js';

function getSectorsFilter() {
  return [
    { id: 'tous', label: t('data.filter_all') },
    { id: 'agriculture', label: t('sectors.names.agriculture') },
    { id: 'environment', label: t('sectors.names.environment') },
    { id: 'markets', label: t('sectors.names.markets') },
    { id: 'transport', label: t('sectors.names.transport') },
    { id: 'education', label: t('sectors.names.education') },
    { id: 'economy', label: t('sectors.names.economy') },
  ];
}

let activeSector = 'tous';
let currentLimit = 15;
let sortAsc = false;
let isGridView = false;
let searchQuery = '';
let currentObsData = [];

function formatObsValue(val) {
  const num = Number(val);
  if (isNaN(num)) return val;
  if (Number.isInteger(num)) return num.toLocaleString();
  return num.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 2 });
}

function renderObservationCard(o) {
  const badgeText = o.status || t('common.validated');
  const badgeClass = badgeText === t('common.validated') || badgeText === 'VALIDÉ' || badgeText === 'validated' ? 'badge--valid' : 'badge--cyan';

  return `
    <div class="card obs-card-item" style="padding:16px;">
      <div class="flex justify-between items-start mb-2">
        <span class="badge ${badgeClass}">${badgeText.toUpperCase()}</span>
        <span class="mono-xs text-muted">${(o.sector || 'GENERAL').toUpperCase()}</span>
      </div>
      <div class="mono-2xl fw-700 mb-2" style="color:var(--text);">${formatObsValue(o.value)} <span class="mono-lg" style="color:var(--text-muted);">${o.unit || ''}</span></div>
      <p class="mono-sm flex items-center gap-1"><i data-lucide="map-pin" style="width:14px;height:14px;" class="text-accent"></i> ${o.indicator || 'Observation'} — ${o.region || t('common.location')}</p>
      <p class="mono-xs text-muted mb-4 flex items-center gap-1"><i data-lucide="calendar" style="width:12px;height:12px;"></i> ${o.reference_date || o.collected_at || t('common.date')}</p>
      <div class="separator flex justify-between items-center pt-2">
        <span class="mono-xs text-muted">${t('common.source')}: ${(o.source || 'FreeData').toUpperCase()}</span>
        <span class="mono-xs text-muted">${o.country_code || 'TCH'}</span>
      </div>
    </div>`;
}

export const DataView = {
  render(params = {}) {
    const initSector = (params.sector || 'tous').toLowerCase();
    activeSector = initSector;
    const sectorsFilter = getSectorsFilter();

    return `
      <div class="flex justify-between items-start mb-4">
        <div>
          <h2 class="hero-title uppercase" style="font-size:20px;margin-bottom:0;">${t('data.title')}</h2>
        </div>
        <button class="btn btn-cyan" id="btn-data-harvest">
          <i data-lucide="zap" style="width:16px;height:16px;"></i> ${t('common.collect')}
        </button>
      </div>

      <div class="flex gap-2 mb-6">
        <div style="flex:1;">
          <input class="input-search" type="text" placeholder="${t('data.search')}" id="search-obs" value="${searchQuery}">
        </div>
        <button class="btn btn-ghost" id="btn-grid-toggle" style="padding:0 16px;" title="Changer d'affichage Grid/Liste" aria-label="Toggle View Layout">
          <i data-lucide="${isGridView ? 'list' : 'layout-grid'}" style="width:16px;height:16px;"></i>
        </button>
      </div>

      <div class="mb-6">
        <h4 class="mono-xs text-muted uppercase mb-2">${t('data.sectors_label')}</h4>
        <div class="flex gap-2 flex-wrap" id="sector-filter-buttons">
          ${sectorsFilter.map(s => {
            const isActive = s.id === activeSector;
            return `<button class="btn ${isActive ? 'btn-cyan' : 'btn-ghost'} filter-sector-btn mono-sm" data-sector="${s.id}">${s.label}</button>`;
          }).join('')}
        </div>
      </div>

      <div class="flex justify-between items-center mb-4">
        <h4 class="uppercase" style="font-size:14px;" id="obs-count-header">${t('data.obs_header')} (${t('common.loading')})</h4>
        <span class="mono-xs text-cyan cursor-pointer flex items-center gap-1" id="btn-sort-toggle">
          <i data-lucide="arrow-up-down" style="width:12px;height:12px;"></i> ${t('data.sort_label')} ${sortAsc ? '▲' : '▼'}
        </span>
      </div>

      <div id="obs-list-container" class="${isGridView ? 'grid-2 mb-4' : 'flex flex-col gap-3 mb-4'}">
        <div class="card" style="padding:24px;text-align:center;" id="obs-loading-indicator">
          <p class="mono-sm text-muted">${t('data.loading_db')}</p>
        </div>
      </div>

      <!-- Live Dynamic Trend Chart -->
      <div class="card mt-4 mb-4" style="padding:16px;border-color:var(--border-strong);" id="chart-section-card">
        <h4 class="mono-sm uppercase mb-4 text-cyan flex items-center gap-2">
          <i data-lucide="line-chart" style="width:16px;height:16px;"></i> ${t('data.trend_title')}
        </h4>
        <div class="chart-container" style="height:160px;">
          <canvas id="chart-mais"></canvas>
        </div>
        <div class="separator flex justify-between items-center mt-4">
          <span class="mono-xs text-muted">${t('data.trend_footer')}</span>
          <span class="mono-sm text-accent">${t('data.live')}</span>
        </div>
      </div>

      <div class="mt-4 mb-6">
        <button class="btn btn-ghost w-full justify-center mono-sm" id="btn-load-more" style="padding:12px;">
          <i data-lucide="plus" style="width:16px;height:16px;"></i> ${t('data.load_more')}
        </button>
      </div>
    `;
  },

  async init(params = {}) {
    if (window.lucide) window.lucide.createIcons();

    // 1. Sector Filter Buttons
    document.querySelectorAll('.filter-sector-btn').forEach(btn => {
      btn.addEventListener('click', async (e) => {
        const sec = e.currentTarget.getAttribute('data-sector');
        activeSector = sec;

        document.querySelectorAll('.filter-sector-btn').forEach(b => {
          b.classList.remove('btn-cyan');
          b.classList.add('btn-ghost');
        });
        e.currentTarget.classList.remove('btn-ghost');
        e.currentTarget.classList.add('btn-cyan');

        currentLimit = 15;
        await DataView.loadDynamicData();
      });
    });

    // 3. Active Search Input Filter
    const searchInput = document.getElementById('search-obs');
    if (searchInput) {
      searchInput.addEventListener('input', (e) => {
        searchQuery = e.target.value;
        DataView.renderObsList();
      });
    }

    // 4. Grid / List View Layout Toggle Button
    const gridToggleBtn = document.getElementById('btn-grid-toggle');
    if (gridToggleBtn) {
      gridToggleBtn.addEventListener('click', () => {
        isGridView = !isGridView;
        const container = document.getElementById('obs-list-container');
        if (container) {
          container.className = isGridView ? 'grid-2 mb-4' : 'flex flex-col gap-3 mb-4';
        }
        gridToggleBtn.innerHTML = `<i data-lucide="${isGridView ? 'list' : 'layout-grid'}" style="width:16px;height:16px;"></i>`;
        if (window.lucide) window.lucide.createIcons();
      });
    }

    // 5. Sort toggle
    const sortBtn = document.getElementById('btn-sort-toggle');
    if (sortBtn) {
      sortBtn.addEventListener('click', () => {
        sortAsc = !sortAsc;
        sortBtn.innerHTML = `<i data-lucide="arrow-up-down" style="width:12px;height:12px;"></i> ${t('data.sort_label')} ${sortAsc ? '▲' : '▼'}`;
        if (window.lucide) window.lucide.createIcons();
        DataView.renderObsList();
      });
    }

    // 6. Load More Button
    const loadMoreBtn = document.getElementById('btn-load-more');
    if (loadMoreBtn) {
      loadMoreBtn.addEventListener('click', async () => {
        currentLimit += 25;
        loadMoreBtn.innerHTML = `<i data-lucide="loader" class="animate-spin" style="width:16px;height:16px;"></i> ${t('common.loading')}`;
        if (window.lucide) window.lucide.createIcons();
        await DataView.loadDynamicData();
      });
    }

    // 7. Wire "COLLECT LIVE DATA" button
    const btnHarvest = document.getElementById('btn-data-harvest');
    if (btnHarvest) {
      btnHarvest.addEventListener('click', async () => {
        btnHarvest.disabled = true;
        btnHarvest.innerHTML = `<i data-lucide="loader" class="animate-spin" style="width:16px;height:16px;"></i> ${t('common.loading')}`;
        if (window.lucide) window.lucide.createIcons();

        try {
          if (activeSector === 'environment') {
            await triggerEnvironmentHarvest('all');
          } else if (activeSector === 'markets') {
            await triggerMarketsHarvest('all');
          } else if (activeSector === 'economy') {
            await triggerEconomyHarvest('all');
          } else {
            await triggerAgricultureHarvest('all');
          }
          alert(t('common.harvest_ok'));
          await DataView.loadDynamicData();
        } catch (err) {
          alert('Harvest failed: ' + err.message);
        } finally {
          btnHarvest.disabled = false;
          btnHarvest.innerHTML = `<i data-lucide="zap" style="width:16px;height:16px;"></i> ${t('common.collect')}`;
          if (window.lucide) window.lucide.createIcons();
        }
      });
    }

    // Initial load
    await DataView.loadDynamicData();
  },

  async loadDynamicData() {
    const container = document.getElementById('obs-list-container');
    const header = document.getElementById('obs-count-header');
    const loadMoreBtn = document.getElementById('btn-load-more');

    try {
      const data = await fetchObservations(activeSector, currentLimit);
      currentObsData = data || [];

      if (loadMoreBtn) {
        loadMoreBtn.innerHTML = `<i data-lucide="plus" style="width:16px;height:16px;"></i> ${t('data.load_more')}`;
        if (window.lucide) window.lucide.createIcons();
      }

      // Render chart using real backend values
      initChartMais(currentObsData);

      DataView.renderObsList();
    } catch (err) {
      console.warn('DataView load error:', err);
      if (container) {
        container.innerHTML = `<div class="card" style="padding:16px;"><p class="mono-sm text-accent">${t('common.error')}</p></div>`;
      }
    }
  },

  renderObsList() {
    const container = document.getElementById('obs-list-container');
    const header = document.getElementById('obs-count-header');
    if (!container) return;

    let filtered = [...currentObsData];

    // Filter by search query across all observation fields
    if (searchQuery.trim() !== '') {
      const q = searchQuery.toLowerCase().trim();
      filtered = filtered.filter(o =>
        (o.indicator || '').toLowerCase().includes(q) ||
        (o.sector || '').toLowerCase().includes(q) ||
        (o.region || '').toLowerCase().includes(q) ||
        (o.source || '').toLowerCase().includes(q) ||
        (o.unit || '').toLowerCase().includes(q) ||
        String(o.value || '').toLowerCase().includes(q) ||
        (o.reference_date || '').toLowerCase().includes(q)
      );
    }

    // Update count header
    if (header) {
      header.textContent = `${t('data.obs_header')} : ${filtered.length}`;
    }

    let sorted = filtered;
    sorted.sort((a, b) => {
      const dateA = new Date(a.reference_date || a.collected_at || 0);
      const dateB = new Date(b.reference_date || b.collected_at || 0);
      return sortAsc ? dateA - dateB : dateB - dateA;
    });

    if (sorted.length === 0) {
      container.innerHTML = `
        <div class="card mb-4" style="padding:24px;text-align:center;grid-column:1/-1;">
          <p class="mono-sm text-muted mb-3">${t('data.empty_msg')} "${activeSector.toUpperCase()}".</p>
          <button class="btn btn-cyan mono-sm" id="btn-empty-harvest">
            <i data-lucide="zap" style="width:16px;height:16px;"></i> ${t('data.empty_btn')}
          </button>
        </div>
      `;
      if (window.lucide) window.lucide.createIcons();

      const emptyHarvestBtn = document.getElementById('btn-empty-harvest');
      if (emptyHarvestBtn) {
        emptyHarvestBtn.addEventListener('click', async () => {
          emptyHarvestBtn.disabled = true;
          emptyHarvestBtn.innerHTML = `<i data-lucide="loader" class="animate-spin" style="width:16px;height:16px;"></i> ${t('data.harvest_loading')}`;
          if (window.lucide) window.lucide.createIcons();

          try {
            await triggerAgricultureHarvest('all');
            alert(t('common.harvest_ok'));
            await DataView.loadDynamicData();
          } catch (err) {
            alert(`${t('common.harvest_err')}: ${err.message}`);
          }
        });
      }
      return;
    }

    container.innerHTML = sorted.map(renderObservationCard).join('');
    if (window.lucide) window.lucide.createIcons();
  }
};
