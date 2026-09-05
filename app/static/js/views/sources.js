/**
 * View: Official Data Sources Directory — Dedicated Transparency View
 */

import { OFFICIAL_SOURCES } from '../sources_catalog.js';
import { getLang, t } from '../i18n.js';

function renderSourceCard(src) {
  const lang = getLang();
  const desc = lang === 'en' ? (src.desc_en || src.desc_fr) : src.desc_fr;
  const org  = lang === 'en' ? (src.org_en || src.org_fr) : src.org_fr;
  const sec  = lang === 'en' ? (src.sector_en || src.sector_fr) : src.sector_fr;

  return `
    <div class="card source-directory-item" style="padding:20px;background:var(--surface);border:1px solid var(--border);border-radius:6px;" data-id="${src.id}">
      <div class="flex justify-between items-start mb-3 flex-wrap gap-2">
        <div>
          <div class="flex items-center gap-2 mb-1">
            <span class="mono-xs badge badge--cyan">${sec.toUpperCase()}</span>
            <span class="mono-xs badge badge--valid">${src.license}</span>
          </div>
          <h3 class="mono-xl fw-700" style="color:var(--text);margin-top:4px;">${src.name}</h3>
          <p class="mono-xs text-cyan flex items-center gap-1 mt-1">
            <i data-lucide="building-2" style="width:14px;height:14px;"></i> ${org}
          </p>
        </div>
        <a href="${src.url}" target="_blank" rel="noopener noreferrer" class="btn btn-cyan mono-sm flex items-center gap-1" style="padding:8px 16px;text-decoration:none;">
          <i data-lucide="external-link" style="width:14px;height:14px;"></i> ${t('sources.open_portal')}
        </a>
      </div>

      <p class="mono-sm text-muted mb-4" style="line-height:1.5;">${desc}</p>

      <div class="separator flex justify-between items-center pt-3">
        <span class="mono-xs text-muted flex items-center gap-1">
          <i data-lucide="shield-check" style="width:12px;height:12px;" class="text-green"></i> Verified Open Data Source
        </span>
        <span class="mono-xs text-muted">${src.url}</span>
      </div>
    </div>`;
}

export const SourcesView = {
  render() {
    return `
      <div class="flex justify-between items-start mb-6 flex-wrap gap-3">
        <div>
          <div class="mono-xs text-cyan fw-700 mb-1 flex items-center gap-1 uppercase">
            <i data-lucide="database" style="width:14px;height:14px;"></i> ${t('sources.badge_count')}
          </div>
          <h2 class="hero-title uppercase" style="font-size:24px;">${t('sources.title')}</h2>
          <p class="hero-subtitle mono-sm text-muted mt-1">${t('sources.subtitle')}</p>
        </div>
        <span class="badge badge--valid mono-sm flex items-center gap-1" style="padding:6px 12px;">
          <i data-lucide="check-circle-2" style="width:14px;height:14px;"></i> 10/10 OK
        </span>
      </div>

      <div class="mb-6">
        <input class="input-search" type="text" placeholder="${t('sources.search')}" id="search-sources-input">
      </div>

      <div class="flex flex-col gap-4 mb-8" id="sources-catalog-container">
        ${OFFICIAL_SOURCES.map(renderSourceCard).join('')}
      </div>
    `;
  },

  init() {
    if (window.lucide) window.lucide.createIcons();

    // Active Search Filtering across source details
    const searchInput = document.getElementById('search-sources-input');
    if (searchInput) {
      searchInput.addEventListener('input', (e) => {
        const q = e.target.value.toLowerCase().trim();
        document.querySelectorAll('.source-directory-item').forEach(card => {
          const text = card.textContent.toLowerCase();
          card.style.display = text.includes(q) ? '' : 'none';
        });
      });
    }
  }
};
