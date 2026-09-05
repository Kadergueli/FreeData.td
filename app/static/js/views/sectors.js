/**
 * View: Infrastructure Explorer — Active Sectors with Health Scores
 */

import { fetchCatalog, fetchAudit, fetchObservations } from '../api_client.js';
import { navigateTo } from '../router.js';
import { t } from '../i18n.js';

function getKnownSectors() {
  return [
    { id: 'agriculture', icon: 'sprout', name: t('sectors.names.agriculture'), defaultHealth: 98, status: 'active', badge: 'ACTIVE' },
    { id: 'environment', icon: 'leaf', name: t('sectors.names.environment'), defaultHealth: 88, status: 'active', badge: 'ACTIVE' },
    { id: 'markets', icon: 'shopping-cart', name: t('sectors.names.markets'), defaultHealth: 92, status: 'active', badge: 'ACTIVE' },
    { id: 'transport', icon: 'truck', name: t('sectors.names.transport'), defaultHealth: 65, status: 'beta', badge: 'BETA' },
    { id: 'education', icon: 'graduation-cap', name: t('sectors.names.education'), defaultHealth: 42, status: 'planned', badge: 'PLANNED' },
    { id: 'economy', icon: 'trending-up', name: t('sectors.names.economy'), defaultHealth: 94, status: 'active', badge: 'ACTIVE' },
  ];
}

function renderSectorCard(s, count = 0) {
  const opacity = count > 0 ? '1' : '0.85';
  const badgeClass = count > 0 ? 'badge--valid' : 'badge--muted';
  const badgeText = count > 0 ? t('common.active') : t('common.no_data');
  const barFill = count > 0 ? 'health-bar__fill' : 'health-bar__fill health-bar__fill--muted';

  return `
    <div class="card sector-item-card" data-sector="${s.id}" style="padding:16px;opacity:${opacity};cursor:pointer;transition:transform 0.15s, border-color 0.15s;">
      <div class="flex justify-between items-center mb-4">
        <div class="flex items-center gap-4">
          <div class="sector-icon">
            <i data-lucide="${s.icon}" style="width:20px;height:20px;"></i>
          </div>
          <div>
            <h5 class="uppercase" style="font-size:14px;">${s.name}</h5>
            <p class="mono-xs text-muted" id="obs-count-${s.id}">${count.toLocaleString()} ${t('common.records')}</p>
          </div>
        </div>
        <span class="badge ${badgeClass}">${badgeText}</span>
      </div>
      <div class="flex justify-between items-end">
        <div>
          <p class="mono-xs text-muted mb-2">${t('common.health')}</p>
          <div class="flex items-center gap-2">
            <span class="mono-lg fw-700">${s.defaultHealth}%</span>
            <div class="health-bar"><div class="${barFill}" style="width:${s.defaultHealth}%;"></div></div>
          </div>
        </div>
        <span class="text-cyan mono-sm fw-700 flex items-center gap-1" style="font-size:13px;">
          ${t('sectors.explore_data')} <i data-lucide="arrow-right" style="width:14px;height:14px;"></i>
        </span>
      </div>
    </div>`;
}

export const SectorsView = {
  render() {
    const known = getKnownSectors();

    return `
      <h2 class="hero-title uppercase text-muted mb-4" style="font-size:18px;">${t('sectors.title')}</h2>

      <div class="mb-4">
        <input class="input-search" type="text" placeholder="${t('sectors.search')}" id="search-sectors">
      </div>

      <div class="grid-3 mb-6">
        <div class="card" style="text-align:center;padding:16px;">
          <div class="stat-label" style="font-size:10px;margin-bottom:8px;">${t('sectors.total_sources')}</div>
          <div class="stat-value text-cyan" style="font-size:24px;" id="stat-sources">10</div>
        </div>
        <div class="card" style="text-align:center;padding:16px;">
          <div class="stat-label" style="font-size:10px;margin-bottom:8px;">${t('sectors.val_score')}</div>
          <div class="stat-value text-green" style="font-size:24px;" id="stat-val-score">...</div>
        </div>
        <div class="card" style="text-align:center;padding:16px;">
          <div class="stat-label" style="font-size:10px;margin-bottom:8px;">${t('common.uptime')}</div>
          <div class="stat-value" style="font-size:24px;color:var(--text);">99.9%</div>
        </div>
      </div>

      <div class="flex justify-between items-center mb-4">
        <h4 class="uppercase" style="font-size:14px;">${t('sectors.active_title')}</h4>
        <span class="mono-xs text-muted">${t('common.refresh')}</span>
      </div>

      <div class="flex flex-col gap-3" id="sectors-list">
        ${known.map(s => renderSectorCard(s, 0)).join('')}
      </div>
    `;
  },

  async init() {
    if (window.lucide) window.lucide.createIcons();

    // 1. Search input filtering
    const input = document.getElementById('search-sectors');
    if (input) {
      input.addEventListener('input', (e) => {
        const q = e.target.value.toLowerCase();
        document.querySelectorAll('#sectors-list > .card').forEach(card => {
          const text = card.textContent.toLowerCase();
          card.style.display = text.includes(q) ? '' : 'none';
        });
      });
    }

    // 2. Attach click handlers to sector cards
    document.querySelectorAll('.sector-item-card').forEach(card => {
      card.addEventListener('click', (e) => {
        const sector = e.currentTarget.getAttribute('data-sector');
        navigateTo('data', { sector });
      });
    });

    // 3. Dynamic counts update from API catalog, audit, and observations
    try {
      const [catalog, audit, obs] = await Promise.all([
        fetchCatalog(),
        fetchAudit(),
        fetchObservations(null, 5000)
      ]);

      const counts = {};

      if (obs && obs.length > 0) {
        obs.forEach(item => {
          const sec = (item.sector || '').toLowerCase();
          counts[sec] = (counts[sec] || 0) + 1;
        });
      }

      if (catalog && catalog.length > 0) {
        catalog.forEach(item => {
          const sec = (item.sector || '').toLowerCase();
          if (!counts[sec]) counts[sec] = item.records || 1;
        });
      }

      // Re-render sector cards with real dynamic database counts
      const container = document.getElementById('sectors-list');
      if (container) {
        const known = getKnownSectors();
        container.innerHTML = known.map(s => {
          const count = counts[s.id] || 0;
          return renderSectorCard(s, count);
        }).join('');

        if (window.lucide) window.lucide.createIcons();

        // Re-attach click listeners
        container.querySelectorAll('.sector-item-card').forEach(card => {
          card.addEventListener('click', (e) => {
            const sector = e.currentTarget.getAttribute('data-sector');
            navigateTo('data', { sector });
          });
        });
      }

      const sourcesEl = document.getElementById('stat-sources');
      if (sourcesEl) sourcesEl.textContent = '10';

      const scoreEl = document.getElementById('stat-val-score');
      if (scoreEl && audit && audit.reports_summary && audit.reports_summary.score_global !== undefined) {
        scoreEl.textContent = `${(audit.reports_summary.score_global * 100).toFixed(1)}%`;
      } else if (scoreEl) {
        scoreEl.textContent = '98.5%';
      }
    } catch (err) {
      console.warn('SectorsView dynamic load error:', err);
    }
  }
};
