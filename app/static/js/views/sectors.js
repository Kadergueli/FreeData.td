/**
 * View: Infrastructure Explorer — one card per sector, with REAL observation counts.
 *
 * Every number comes from /api/v1/stats (or the static sources catalog). Nothing is
 * hard-coded: a value that cannot be read is shown as "—" rather than invented.
 */

import { fetchStats, fetchAudit } from '../api_client.js';
import { OFFICIAL_SOURCES } from '../sources_catalog.js';
import { t } from '../i18n.js';
import { escapeHtml } from '../sanitize.js';

const TOTAL_CHAD_REGIONS = 23;

function getKnownSectors() {
  return [
    { id: 'agriculture', icon: 'sprout', name: t('sectors.names.agriculture') },
    { id: 'environment', icon: 'leaf', name: t('sectors.names.environment') },
    { id: 'markets', icon: 'shopping-cart', name: t('sectors.names.markets') },
    { id: 'health', icon: 'heart-pulse', name: t('sectors.names.health') },
    { id: 'energy', icon: 'zap', name: t('sectors.names.energy') },
    { id: 'transport', icon: 'truck', name: t('sectors.names.transport') },
    { id: 'education', icon: 'graduation-cap', name: t('sectors.names.education') },
    { id: 'economy', icon: 'trending-up', name: t('sectors.names.economy') },
  ];
}

/** count: number | null (null = still loading, undefined = unknown) ; total: all observations */
function renderSectorCard(s, count, total) {
  const loading = count === null;
  const unknown = count === undefined;
  const hasData = typeof count === 'number' && count > 0;

  const badgeClass = hasData ? 'badge--valid' : 'badge--muted';
  const badgeText = loading ? '…' : unknown ? '—' : hasData ? t('common.active') : t('common.no_data');
  const countText = loading
    ? '<span class="skeleton" style="width:90px;"></span>'
    : unknown ? '—' : `${count.toLocaleString()} ${t('common.records')}`;
  const share = hasData && total > 0 ? Math.max(1, Math.round((count / total) * 100)) : 0;
  const shareText = hasData && total > 0 ? `${share}%` : '—';
  const barFill = hasData ? 'health-bar__fill' : 'health-bar__fill health-bar__fill--muted';

  return `
    <a class="card sector-item-card" href="#/data?sector=${encodeURIComponent(s.id)}" data-sector="${escapeHtml(s.id)}"
       style="padding:16px;text-decoration:none;color:inherit;display:block;">
      <div class="flex justify-between items-center mb-4">
        <div class="flex items-center gap-4">
          <div class="sector-icon">
            <i data-lucide="${s.icon}" style="width:20px;height:20px;"></i>
          </div>
          <div>
            <h5 class="uppercase" style="font-size:14px;">${escapeHtml(s.name)}</h5>
            <p class="mono-xs text-muted">${countText}</p>
          </div>
        </div>
        <span class="badge ${badgeClass}">${badgeText}</span>
      </div>
      <div class="flex justify-between items-end">
        <div>
          <p class="mono-xs text-muted mb-2">${t('sectors.share')}</p>
          <div class="flex items-center gap-2">
            <span class="mono-lg fw-700">${shareText}</span>
            <div class="health-bar"><div class="${barFill}" style="width:${share}%;"></div></div>
          </div>
        </div>
        <span class="text-cyan mono-sm fw-700 flex items-center gap-1" style="font-size:13px;">
          ${t('sectors.explore_data')} <i data-lucide="arrow-right" style="width:14px;height:14px;"></i>
        </span>
      </div>
    </a>`;
}

export const SectorsView = {
  render() {
    const known = getKnownSectors();
    return `
      <h2 class="hero-title uppercase text-muted mb-4" style="font-size:18px;">${t('sectors.title')}</h2>

      <div class="mb-4">
        <input class="input-search" type="text" placeholder="${t('sectors.search')}" id="search-sectors" aria-label="${t('sectors.search')}">
      </div>

      <div class="grid-3 mb-6">
        <div class="card" style="text-align:center;padding:16px;">
          <div class="stat-label" style="font-size:10px;margin-bottom:8px;">${t('sectors.total_sources')}</div>
          <div class="stat-value text-cyan" style="font-size:24px;" id="stat-sources">${OFFICIAL_SOURCES.length}</div>
        </div>
        <div class="card" style="text-align:center;padding:16px;">
          <div class="stat-label" style="font-size:10px;margin-bottom:8px;">${t('sectors.val_score')}</div>
          <div class="stat-value text-green" style="font-size:24px;" id="stat-val-score"><span class="skeleton"></span></div>
        </div>
        <div class="card" style="text-align:center;padding:16px;">
          <div class="stat-label" style="font-size:10px;margin-bottom:8px;">${t('sectors.regions_covered')}</div>
          <div class="stat-value" style="font-size:24px;color:var(--text);" id="stat-regions"><span class="skeleton"></span></div>
        </div>
      </div>

      <div class="flex justify-between items-center mb-4">
        <h4 class="uppercase" style="font-size:14px;">${t('sectors.active_title')}</h4>
        <span class="mono-xs text-muted">${t('common.refresh')}</span>
      </div>

      <div class="flex flex-col gap-3" id="sectors-list">
        ${known.map(s => renderSectorCard(s, null, 0)).join('')}
      </div>
      <p class="mono-sm text-muted" id="sectors-no-match" style="display:none;" role="status">${t('sectors.no_match')}</p>
    `;
  },

  async init() {
    // Search: wired immediately (does not wait for the network).
    const input = document.getElementById('search-sectors');
    if (input) {
      input.addEventListener('input', (e) => {
        const q = e.target.value.toLowerCase().trim();
        let visible = 0;
        document.querySelectorAll('#sectors-list > .card').forEach(card => {
          const match = card.textContent.toLowerCase().includes(q);
          card.style.display = match ? '' : 'none';
          if (match) visible += 1;
        });
        const none = document.getElementById('sectors-no-match');
        if (none) none.style.display = visible === 0 ? '' : 'none';
      });
    }

    const [statsRes, auditRes] = await Promise.allSettled([fetchStats(), fetchAudit()]);
    const stats = statsRes.status === 'fulfilled' ? statsRes.value : null;
    const audit = auditRes.status === 'fulfilled' ? auditRes.value : null;

    const container = document.getElementById('sectors-list');
    if (!container) return; // user already left the page

    const total = stats ? Number(stats.total || 0) : 0;
    container.innerHTML = getKnownSectors().map(s => {
      // stats missing → unknown; sector absent from stats → either 0 rows or a failed count
      // (the API omits failed sectors) — we only claim "no data" when the total itself is known to be positive.
      const count = stats && stats.sectors
        ? (s.id in stats.sectors ? Number(stats.sectors[s.id]) : (total === 0 ? 0 : undefined))
        : undefined;
      return renderSectorCard(s, count, total);
    }).join('');
    if (window.lucide) window.lucide.createIcons();

    const q = input ? input.value : '';
    if (q) input.dispatchEvent(new Event('input'));

    const scoreEl = document.getElementById('stat-val-score');
    if (scoreEl) {
      const raw = audit && audit.reports_summary ? audit.reports_summary.score_global : null;
      scoreEl.textContent = typeof raw === 'number' ? `${(raw * 100).toFixed(1)}%` : '—';
    }

    const regEl = document.getElementById('stat-regions');
    if (regEl) {
      regEl.textContent = stats && stats.regions
        ? `${Math.min(Object.keys(stats.regions).length, TOTAL_CHAD_REGIONS)} / ${TOTAL_CHAD_REGIONS}`
        : '—';
    }
  },
};
