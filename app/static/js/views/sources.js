/**
 * View: Public data sources directory.
 * The count comes from the catalog itself (no hard-coded "12"), and no "verified" /
 * "12/12 OK" claim is made: the page lists sources, it does not probe them.
 */

import { OFFICIAL_SOURCES } from '../sources_catalog.js';
import { getLang, t } from '../i18n.js';
import { escapeHtml } from '../sanitize.js';

function hostOf(url) {
  try { return new URL(url).hostname; } catch (_) { return String(url || ''); }
}

function renderSourceCard(src) {
  const en = getLang() === 'en';
  const desc = en ? (src.desc_en || src.desc_fr) : src.desc_fr;
  const org  = en ? (src.org_en || src.org_fr) : src.org_fr;
  const sec  = en ? (src.sector_en || src.sector_fr) : src.sector_fr;
  const lic  = (en ? src.license : src.license_fr) || src.license;

  // Folded by default: a directory of 15 open cards was ~5,000 px tall on a phone.
  return `
    <details class="card source-directory-item source-item" data-id="${escapeHtml(src.id)}" data-sector="${escapeHtml(src.sectorId || '')}">
      <summary class="source-summary">
        <div style="min-width:0;flex:1;">
          <h3 class="source-name">${escapeHtml(src.name)}</h3>
          <p class="mono-xs text-cyan source-org">${escapeHtml(org)}</p>
          <div class="flex items-center gap-2 flex-wrap mt-1">
            <span class="mono-xs badge badge--cyan">${escapeHtml(String(sec).toUpperCase())}</span>
            <span class="mono-xs badge badge--valid">${escapeHtml(lic)}</span>
          </div>
        </div>
        <span class="source-chev" aria-hidden="true">▾</span>
      </summary>
      <div class="source-body">
        <p class="mono-sm text-muted mb-3" style="line-height:1.5;">${escapeHtml(desc)}</p>
        <div class="flex justify-between items-center flex-wrap gap-2">
          <span class="mono-xs text-muted">${escapeHtml(hostOf(src.url))}</span>
          <a href="${escapeHtml(src.url)}" target="_blank" rel="noopener noreferrer" class="btn btn-cyan mono-sm flex items-center gap-1" style="padding:8px 16px;text-decoration:none;">
            <i data-lucide="external-link" style="width:14px;height:14px;"></i> ${t('sources.open_portal')}
          </a>
        </div>
      </div>
    </details>`;
}

export const SourcesView = {
  render() {
    const n = OFFICIAL_SOURCES.length;
    return `
      <div class="flex justify-between items-start mb-6 flex-wrap gap-3">
        <div>
          <div class="mono-xs text-cyan fw-700 mb-1 flex items-center gap-1 uppercase" id="sources-count-label">
            <i data-lucide="database" style="width:14px;height:14px;"></i> ${t('sources.badge_count').replace('{n}', n)}
          </div>
          <h2 class="hero-title uppercase" style="font-size:24px;">${t('sources.title')}</h2>
          <p class="hero-subtitle mono-sm text-muted mt-1">${t('sources.subtitle')}</p>
        </div>
      </div>

      <div class="mb-6">
        <input class="input-search" type="text" placeholder="${escapeHtml(t('sources.search'))}" id="search-sources-input" aria-label="${escapeHtml(t('sources.search'))}">
      </div>

      <div class="flex gap-2 flex-wrap mb-6" id="sources-sector-filter">
        ${['all', ...new Set(OFFICIAL_SOURCES.map(x => x.sectorId).filter(Boolean))].map(id => `<button type="button" class="btn ${id === 'all' ? 'btn-cyan' : 'btn-ghost'} mono-sm" data-filter="${escapeHtml(id)}" aria-pressed="${id === 'all'}">${escapeHtml(id === 'all' ? t('data.filter_all') : t('sectors.names.' + id))}</button>`).join('')}
      </div>

      <div class="flex flex-col gap-3 mb-8" id="sources-catalog-container">
        ${OFFICIAL_SOURCES.map(renderSourceCard).join('')}
        <p class="mono-sm text-muted" id="sources-no-match" style="display:none;">${t('sources.no_match')}</p>
      </div>
    `;
  },

  init() {
    if (window.lucide) window.lucide.createIcons();

    const searchInput = document.getElementById('search-sources-input');
    let sector = 'all';
    const apply = () => {
      const q = searchInput ? searchInput.value.toLowerCase().trim() : '';
      let shown = 0;
      document.querySelectorAll('.source-directory-item').forEach(card => {
        const ok = (sector === 'all' || card.getAttribute('data-sector') === sector)
          && card.textContent.toLowerCase().includes(q);
        card.style.display = ok ? '' : 'none';
        if (ok) shown++;
      });
      const none = document.getElementById('sources-no-match');
      if (none) none.style.display = shown === 0 ? '' : 'none';
    };
    if (searchInput) searchInput.addEventListener('input', apply);
    document.getElementById('sources-sector-filter')?.addEventListener('click', (e) => {
      const b = e.target.closest('[data-filter]');
      if (!b) return;
      sector = b.getAttribute('data-filter');
      document.querySelectorAll('#sources-sector-filter [data-filter]').forEach(x => {
        const on = x === b;
        x.classList.toggle('btn-cyan', on);
        x.classList.toggle('btn-ghost', !on);
        x.setAttribute('aria-pressed', String(on));
      });
      apply();
    });
  },
};
