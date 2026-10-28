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

  return `
    <div class="card source-directory-item" style="padding:20px;background:var(--surface);border:1px solid var(--border);border-radius:6px;" data-id="${escapeHtml(src.id)}">
      <div class="flex justify-between items-start mb-3 flex-wrap gap-2">
        <div>
          <div class="flex items-center gap-2 mb-1">
            <span class="mono-xs badge badge--cyan">${escapeHtml(String(sec).toUpperCase())}</span>
            <span class="mono-xs badge badge--valid">${escapeHtml((en ? src.license : src.license_fr) || src.license)}</span>
          </div>
          <h3 class="mono-xl fw-700" style="color:var(--text);margin-top:4px;">${escapeHtml(src.name)}</h3>
          <p class="mono-xs text-cyan flex items-center gap-1 mt-1">
            <i data-lucide="building-2" style="width:14px;height:14px;"></i> ${escapeHtml(org)}
          </p>
        </div>
        <a href="${escapeHtml(src.url)}" target="_blank" rel="noopener noreferrer" class="btn btn-cyan mono-sm flex items-center gap-1" style="padding:8px 16px;text-decoration:none;">
          <i data-lucide="external-link" style="width:14px;height:14px;"></i> ${t('sources.open_portal')}
        </a>
      </div>

      <p class="mono-sm text-muted mb-4" style="line-height:1.5;">${escapeHtml(desc)}</p>

      <div class="separator flex justify-between items-center pt-3">
        <span class="mono-xs text-muted flex items-center gap-1">
          <i data-lucide="database" style="width:12px;height:12px;" class="text-cyan"></i> ${t('sources.open_data_source')}
        </span>
        <span class="mono-xs text-muted">${escapeHtml(hostOf(src.url))}</span>
      </div>
    </div>`;
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

      <div class="flex flex-col gap-4 mb-8" id="sources-catalog-container">
        ${OFFICIAL_SOURCES.map(renderSourceCard).join('')}
        <p class="mono-sm text-muted" id="sources-no-match" style="display:none;">${t('sources.no_match')}</p>
      </div>
    `;
  },

  init() {
    if (window.lucide) window.lucide.createIcons();

    const searchInput = document.getElementById('search-sources-input');
    if (!searchInput) return;
    searchInput.addEventListener('input', (e) => {
      const q = e.target.value.toLowerCase().trim();
      let shown = 0;
      document.querySelectorAll('.source-directory-item').forEach(card => {
        const ok = card.textContent.toLowerCase().includes(q);
        card.style.display = ok ? '' : 'none';
        if (ok) shown++;
      });
      const none = document.getElementById('sources-no-match');
      if (none) none.style.display = shown === 0 ? '' : 'none';
    });
  },
};
