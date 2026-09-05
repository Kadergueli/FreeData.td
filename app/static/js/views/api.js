/**
 * View: Export & API — Developer Central
 */

import { getExportUrl } from '../api_client.js';
import { t } from '../i18n.js';

let selectedFormat = 'JSON';
let selectedSector = 'all';
let selectedRegion = 'all';

const FORMATS = ['JSON', 'CSV', 'XML', 'PARQUET'];

const SECTORS = [
  { id: 'all', label: 'Tous les jeux de données' },
  { id: 'agriculture', label: 'Agriculture' },
  { id: 'environment', label: 'Environnement' },
  { id: 'markets', label: 'Marchés & Prix' },
  { id: 'economy', label: 'Économie' },
  { id: 'transport', label: 'Transport' },
  { id: 'education', label: 'Éducation' },
];

const REGIONS = [
  { id: 'all', label: 'National / Tout le Tchad' },
  { id: 'logone', label: 'Logone' },
  { id: 'ndjamena', label: "N'Djamena" },
  { id: 'kanem', label: 'Kanem / Lac' },
];

function getSectorLabel(secId) {
  const found = SECTORS.find(s => s.id === secId);
  return found ? found.label : 'Tous les jeux de données publics';
}

function getRegionLabel(regId) {
  const found = REGIONS.find(r => r.id === regId);
  return found ? found.label : 'Logone / Tchad';
}

export const ApiView = {
  render() {
    const docs = t('api.docs');
    const docList = Array.isArray(docs) ? docs : [
      { id: 'swagger', icon: 'file-text', name: 'Spécification API OpenAPI et Swagger', desc: 'Full endpoint specifications at /docs', link: '/docs' },
      { id: 'redoc',   icon: 'book-open', name: 'Documentation ReDoc', desc: 'Clean ReDoc documentation at /redoc', link: '/redoc' },
      { id: 'health',  icon: 'activity',  name: 'Point d\'Accès Santé Système', desc: 'Test API system status live at /api/v1/health', link: '/api/v1/health' },
    ];

    const currentKey = sessionStorage.getItem('fd_api_key');
    const hasKey = Boolean(currentKey);

    return `
      <div class="flex justify-between items-start mb-6">
        <div>
          <div class="mono-xs text-accent fw-700 mb-1 flex items-center gap-1">
            <i data-lucide="terminal" style="width:14px;height:14px;"></i> ${t('api.dev_label')}
          </div>
          <h2 class="hero-title uppercase" style="font-size:24px;">${t('api.title')}</h2>
        </div>
        <div class="mono-xs text-muted flex items-center gap-1">
          <i data-lucide="map-pin" style="width:12px;height:12px;"></i> ${t('api.coord')}
        </div>
      </div>

      <!-- 01 API ACCESS -->
      <h3 class="mono-lg mb-2 flex items-center gap-2">
        <i data-lucide="key-round" style="width:18px;height:18px;" class="text-cyan"></i> ${t('api.section_access')}
      </h3>
      <p class="mono-sm text-muted mb-4">${t('api.access_desc')}</p>

      <div class="card card--transparent mb-6" style="padding:16px;">
        <div class="flex justify-between items-center mb-4">
          <span class="mono-xs text-muted fw-700">${t('api.api_key_label')}</span>
          <span class="text-cyan cursor-pointer flex items-center gap-1" id="btn-copy-key" style="font-size:14px;${hasKey ? '' : 'opacity:0.4;pointer-events:none;'}" title="Copy to Clipboard">
            <i data-lucide="copy" style="width:14px;height:14px;"></i> <span id="copy-status" class="mono-xs text-green"></span>
          </span>
        </div>
        <div class="mono-md word-break-all" id="api-key-display" style="background:var(--surface);border:1px solid var(--border);padding:12px;border-radius:4px;margin-bottom:16px;color:${hasKey ? 'var(--text)' : 'var(--text-muted)'};">
          ${hasKey ? currentKey : t('api.no_key_msg')}
        </div>
        <div class="flex gap-2">
          <button class="btn ${hasKey ? 'btn-ghost' : 'btn-cyan'} fw-700" id="btn-regen-key">
            <i data-lucide="${hasKey ? 'refresh-cw' : 'key'}" style="width:14px;height:14px;"></i> ${hasKey ? t('api.regen') : t('api.btn_generate')}
          </button>
          <button class="btn btn-ghost fw-700" id="btn-revoke-key" style="${hasKey ? '' : 'opacity:0.4;pointer-events:none;'}">
            <i data-lucide="x-circle" style="width:14px;height:14px;"></i> ${t('api.revoke')}
          </button>
        </div>
      </div>

      <!-- 02 DATA DOWNLOAD -->
      <h3 class="mono-lg mb-4 flex items-center gap-2">
        <i data-lucide="download" style="width:18px;height:18px;" class="text-cyan"></i> ${t('api.section_download')}
      </h3>

      <div class="card card--transparent mb-6" style="padding:16px;">
        <h4 class="mono-xs text-muted uppercase mb-2">${t('api.format_label')}</h4>
        <div class="flex gap-2 flex-wrap mb-4" id="export-format-buttons">
          ${FORMATS.map(f =>
            `<button class="btn ${f === selectedFormat ? 'btn-cyan' : 'btn-ghost'} export-fmt-btn mono-sm" data-fmt="${f}">${f}</button>`
          ).join('')}
        </div>

        <h4 class="mono-xs text-muted uppercase mb-2">Secteur à exporter</h4>
        <div class="flex gap-2 flex-wrap mb-4" id="export-sector-buttons">
          ${SECTORS.map(s =>
            `<button class="btn ${s.id === selectedSector ? 'btn-cyan' : 'btn-ghost'} export-sec-btn mono-sm" data-sec="${s.id}">${s.label}</button>`
          ).join('')}
        </div>

        <h4 class="mono-xs text-muted uppercase mb-2">Région à exporter</h4>
        <div class="flex gap-2 flex-wrap mb-6" id="export-region-buttons">
          ${REGIONS.map(r =>
            `<button class="btn ${r.id === selectedRegion ? 'btn-cyan' : 'btn-ghost'} export-reg-btn mono-sm" data-reg="${r.id}">${r.label}</button>`
          ).join('')}
        </div>

        <h4 class="mono-xs text-muted uppercase mb-2">${t('api.filters_label')}</h4>
        <div class="flex gap-2 flex-wrap mb-6" id="active-filters-badges">
          <span class="mono-sm" style="background:var(--surface);padding:6px 12px;border:1px solid var(--border);border-radius:4px;" id="badge-sector">
            Secteur : <strong class="text-cyan">${getSectorLabel(selectedSector)}</strong>
          </span>
          <span class="mono-sm" style="background:var(--surface);padding:6px 12px;border:1px solid var(--border);border-radius:4px;" id="badge-region">
            Région : <strong>${getRegionLabel(selectedRegion)}</strong>
          </span>
        </div>

        <button class="btn btn-primary w-full justify-center mono-md fw-700" id="btn-generate-archive" style="padding:12px;">
          <i data-lucide="download-cloud" style="width:18px;height:18px;"></i> ${t('api.btn_archive')} (${selectedFormat})
        </button>
      </div>

      <!-- 03 DOCUMENTATION -->
      <h3 class="mono-lg mb-4 flex items-center gap-2">
        <i data-lucide="book-open-check" style="width:18px;height:18px;" class="text-cyan"></i> ${t('api.section_docs')}
      </h3>

      <div class="flex flex-col gap-3 mb-6">
        ${docList.map(d => `
          <a class="card card--transparent doc-row" href="${d.link}" target="_blank" style="padding:16px;text-decoration:none;color:inherit;">
            <div class="flex items-center gap-4">
              <div class="source-icon" style="border:1px solid var(--border);">
                <i data-lucide="${d.icon}" style="width:18px;height:18px;"></i>
              </div>
              <div>
                <h5 class="mono-md fw-700">${d.name}</h5>
                <p class="mono-xs text-muted">${d.desc}</p>
              </div>
            </div>
            <span class="text-cyan mono-sm fw-700 flex items-center gap-1" style="font-size:13px;">
              ${t('common.open')} <i data-lucide="external-link" style="width:14px;height:14px;"></i>
            </span>
          </a>
        `).join('')}
      </div>

      <!-- Quota Status Card -->
      <div class="card mb-6" style="padding:16px;border-color:var(--border-strong);background:var(--surface);">
        <div class="flex items-start gap-4">
          <i data-lucide="check-circle-2" style="width:20px;height:20px;flex-shrink:0;" class="text-green"></i>
          <div>
            <h5 class="mono-md fw-700 mb-1" style="color:var(--text);">${t('api.rate_title')}</h5>
            <p class="mono-sm text-muted">${t('api.rate_msg')}</p>
          </div>
        </div>
      </div>

      <!-- Status Footer -->
      <div class="separator flex justify-between items-center" style="padding-top:16px;">
        <div>
          <div class="mono-xs text-green fw-700 flex items-center gap-1">
            <i data-lucide="check-circle-2" style="width:12px;height:12px;"></i> ${t('common.status_ok')}
          </div>
          <div class="mono-xs">${t('api.latency')}: 42ms</div>
        </div>
        <i data-lucide="check" style="width:20px;height:20px;" class="text-green"></i>
      </div>
    `;
  },

  init() {
    if (window.lucide) window.lucide.createIcons();

    // 1. Format Selection
    document.querySelectorAll('.export-fmt-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        selectedFormat = e.currentTarget.getAttribute('data-fmt');
        document.querySelectorAll('.export-fmt-btn').forEach(b => {
          b.classList.remove('btn-cyan');
          b.classList.add('btn-ghost');
        });
        e.currentTarget.classList.remove('btn-ghost');
        e.currentTarget.classList.add('btn-cyan');

        const archiveBtn = document.getElementById('btn-generate-archive');
        if (archiveBtn) {
          archiveBtn.innerHTML = `<i data-lucide="download-cloud" style="width:18px;height:18px;"></i> ${t('api.btn_archive')} (${selectedFormat})`;
          if (window.lucide) window.lucide.createIcons();
        }
      });
    });

    // 2. Dynamic Sector Selection
    document.querySelectorAll('.export-sec-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        selectedSector = e.currentTarget.getAttribute('data-sec');
        document.querySelectorAll('.export-sec-btn').forEach(b => {
          b.classList.remove('btn-cyan');
          b.classList.add('btn-ghost');
        });
        e.currentTarget.classList.remove('btn-ghost');
        e.currentTarget.classList.add('btn-cyan');

        const badgeSector = document.getElementById('badge-sector');
        if (badgeSector) {
          badgeSector.innerHTML = `Secteur : <strong class="text-cyan">${getSectorLabel(selectedSector)}</strong>`;
        }
      });
    });

    // 3. Dynamic Region Selection
    document.querySelectorAll('.export-reg-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        selectedRegion = e.currentTarget.getAttribute('data-reg');
        document.querySelectorAll('.export-reg-btn').forEach(b => {
          b.classList.remove('btn-cyan');
          b.classList.add('btn-ghost');
        });
        e.currentTarget.classList.remove('btn-ghost');
        e.currentTarget.classList.add('btn-cyan');

        const badgeRegion = document.getElementById('badge-region');
        if (badgeRegion) {
          badgeRegion.innerHTML = `Région : <strong>${getRegionLabel(selectedRegion)}</strong>`;
        }
      });
    });

    // 4. Generate Archive Button -> Trigger file download with active filters
    const archiveBtn = document.getElementById('btn-generate-archive');
    if (archiveBtn) {
      archiveBtn.addEventListener('click', () => {
        const fmt = selectedFormat.toLowerCase();
        if (fmt === 'json' || fmt === 'csv') {
          const downloadUrl = getExportUrl(fmt, selectedSector);
          window.open(downloadUrl, '_blank');
        } else {
          const msg = t('api.premium_msg').replace('$FMT', selectedFormat);
          alert(msg);
          window.open(getExportUrl('json', selectedSector), '_blank');
        }
      });
    }

    // 3. API Key Generate / Regenerate / Revoke
    const regenBtn = document.getElementById('btn-regen-key');
    const revokeBtn = document.getElementById('btn-revoke-key');
    const keyDisplay = document.getElementById('api-key-display');
    const copyBtn = document.getElementById('btn-copy-key');
    const copyStatus = document.getElementById('copy-status');

    if (regenBtn && keyDisplay) {
      regenBtn.addEventListener('click', () => {
        const randomPart = Math.random().toString(36).substring(2, 10);
        const newKey = `td-live-${Date.now().toString(36)}-${randomPart}-x110`;
        sessionStorage.setItem('fd_api_key', newKey);

        keyDisplay.textContent = newKey;
        keyDisplay.style.color = 'var(--text)';

        regenBtn.className = 'btn btn-ghost fw-700';
        regenBtn.innerHTML = `<i data-lucide="refresh-cw" style="width:14px;height:14px;"></i> ${t('api.regen')}`;

        if (revokeBtn) {
          revokeBtn.style.opacity = '1';
          revokeBtn.style.pointerEvents = 'auto';
        }
        if (copyBtn) {
          copyBtn.style.opacity = '1';
          copyBtn.style.pointerEvents = 'auto';
        }
        if (window.lucide) window.lucide.createIcons();
      });
    }

    if (revokeBtn && keyDisplay) {
      revokeBtn.addEventListener('click', () => {
        sessionStorage.removeItem('fd_api_key');
        keyDisplay.textContent = t('api.revoked_msg');
        keyDisplay.style.color = 'var(--text-muted)';

        if (regenBtn) {
          regenBtn.className = 'btn btn-cyan fw-700';
          regenBtn.innerHTML = `<i data-lucide="key" style="width:14px;height:14px;"></i> ${t('api.btn_generate')}`;
        }
        revokeBtn.style.opacity = '0.4';
        revokeBtn.style.pointerEvents = 'none';
        if (copyBtn) {
          copyBtn.style.opacity = '0.4';
          copyBtn.style.pointerEvents = 'none';
        }
        if (window.lucide) window.lucide.createIcons();
      });
    }

    if (copyBtn && keyDisplay) {
      copyBtn.addEventListener('click', () => {
        const key = keyDisplay.textContent.trim();
        if (!sessionStorage.getItem('fd_api_key')) return;
        navigator.clipboard.writeText(key).then(() => {
          if (copyStatus) {
            copyStatus.textContent = ` ${t('common.copied')}`;
            setTimeout(() => { copyStatus.textContent = ''; }, 2000);
          }
        }).catch(() => {
          alert(`API Key: ${key}`);
        });
      });
    }
  }
};
