/**
 * View: Export & API.
 *
 * - Downloads go through fetch(): an error response (e.g. 503) used to be saved by the
 *   browser as a corrupt ".parquet" file containing the JSON error.
 * - Parquet is offered only when the server reports it can produce it.
 * - No fake API key (the server never recognised it): the read API is open, and the page
 *   says so, with copy-paste examples.
 * - Limits and latency are real values (from /api/v1/health), not hard-coded text.
 */

import { getExportUrl, fetchRegions, fetchHealth } from '../api_client.js';
import { showToast } from '../ui.js';
import { t } from '../i18n.js';
import { escapeHtml } from '../sanitize.js';

let selectedFormat = 'JSON';
let selectedSector = 'all';
let selectedRegion = 'all';
let _downloading = false;

const FORMATS = ['JSON', 'CSV', 'XML', 'PARQUET'];
const SECTOR_IDS = ['all', 'agriculture', 'environment', 'markets', 'health', 'energy', 'economy', 'transport', 'education', 'demography'];

// All 23 official administrative regions of Chad (ISO 3166-2:TD), spelled WITHOUT accents exactly like the
// region names stored with the data (FEWS NET, INSEED): an accented filter would match nothing.
const CHAD_REGIONS = [
  'Batha', 'Barh el Gazel', 'Borkou', 'Chari-Baguirmi', 'Ennedi Est', 'Ennedi Ouest', 'Guera',
  'Hadjer-Lamis', 'Kanem', 'Lac', 'Logone Occidental', 'Logone Oriental', 'Mandoul',
  'Mayo-Kebbi Est', 'Mayo-Kebbi Ouest', 'Moyen-Chari', "N'Djamena", 'Ouaddai', 'Salamat',
  'Sila', 'Tandjile', 'Tibesti', 'Wadi Fira',
];

function getSectorLabel(secId) {
  return secId === 'all' ? t('api.all_datasets') : t(`sectors.names.${secId}`);
}

function getRegionLabel(regId) {
  return regId === 'all' ? t('api.national') : regId;
}

function renderBadges() {
  const sec = document.getElementById('badge-sector');
  const reg = document.getElementById('badge-region');
  if (sec) sec.innerHTML = `${t('api.badge_sector')} : <strong class="text-cyan">${escapeHtml(getSectorLabel(selectedSector))}</strong>`;
  if (reg) reg.innerHTML = `${t('api.badge_region')} : <strong>${escapeHtml(getRegionLabel(selectedRegion))}</strong>`;
}

function setActive(selector, activeEl) {
  document.querySelectorAll(selector).forEach(b => {
    const on = b === activeEl;
    b.classList.toggle('btn-cyan', on);
    b.classList.toggle('btn-ghost', !on);
    b.setAttribute('aria-pressed', String(on));
  });
}

function wireRegionButtons() {
  document.querySelectorAll('.export-reg-btn').forEach(btn => {
    if (btn.dataset.wired) return; // never stack listeners on a button we already wired
    btn.dataset.wired = '1';
    btn.addEventListener('click', (e) => {
      selectedRegion = e.currentTarget.getAttribute('data-reg');
      setActive('.export-reg-btn', e.currentTarget);
      renderBadges();
    });
  });
}

async function loadRegions() {
  // Official 23 regions always shown; extra regions found in the data are appended.
  let dbRegions = [];
  try { dbRegions = await fetchRegions(); } catch (_) { /* non-critical */ }

  const container = document.getElementById('export-region-buttons');
  if (!container) return;

  const official = new Set(CHAD_REGIONS.map(r => r.toLowerCase()));
  // 'Place (Province)' labels (markets, cities) are found by their province: the 23 buttons are enough.
  const extra = dbRegions.filter(r => !official.has(String(r).toLowerCase()) && !String(r).includes('('));

  [...CHAD_REGIONS, ...extra].forEach(region => {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = `btn ${region === selectedRegion ? 'btn-cyan' : 'btn-ghost'} export-reg-btn mono-sm`;
    btn.style.padding = '4px 10px';
    btn.style.fontSize = '12px';
    btn.setAttribute('data-reg', region);
    btn.setAttribute('aria-pressed', String(region === selectedRegion));
    btn.textContent = region;
    container.appendChild(btn);
  });
  wireRegionButtons();
}

/** Download through fetch so failures are reported instead of saved as a broken file. */
async function downloadExport() {
  if (_downloading) return;
  _downloading = true;
  const btn = document.getElementById('btn-generate-archive');
  const idle = btn ? btn.innerHTML : '';
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = `<i data-lucide="loader" class="animate-spin" style="width:18px;height:18px;"></i> ${t('api.downloading')}`;
    if (window.lucide) window.lucide.createIcons();
  }
  try {
    const fmt = selectedFormat.toLowerCase();
    const res = await fetch(getExportUrl(fmt, selectedSector, selectedRegion));
    if (!res.ok) {
      let detail = '';
      try { detail = (await res.json()).detail; } catch (_) { /* not JSON */ }
      throw new Error(detail || `HTTP ${res.status}`);
    }
    if (res.headers.get('X-Export-Rows') === '0') {
      showToast(t('api.export_empty'), 'info');
      return;
    }
    const truncated = res.headers.get('X-Export-Truncated') === 'true';
    const blob = await res.blob();
    const cd = res.headers.get('Content-Disposition') || '';
    const m = /filename="?([^";]+)"?/i.exec(cd);
    const filename = m ? m[1] : `freedatatd-export.${fmt}`;

    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 10000);
    if (truncated) showToast(t('api.export_truncated'), 'info');
  } catch (err) {
    console.warn('export failed:', err);
    showToast(`${t('api.download_failed')}: ${err.message}`, 'error');
  } finally {
    _downloading = false;
    const again = document.getElementById('btn-generate-archive');
    if (again) {
      again.disabled = false;
      again.innerHTML = idle;
      if (window.lucide) window.lucide.createIcons();
    }
  }
}

function exampleBlock() {
  const origin = window.location.origin;
  const lines = [
    `curl "${origin}/api/v1/observations?sector=health&limit=50"`,
    `curl "${origin}/api/v1/observations?q=riz&region=Lac"`,
    `curl "${origin}/api/v1/stats"`,
    `curl -O -J "${origin}/api/v1/export/csv?sector=agriculture"`,
  ];
  return lines;
}

export const ApiView = {
  render() {
    const docs = t('api.docs');
    const docList = Array.isArray(docs) ? docs : [];
    const examples = exampleBlock();

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

      <!-- 01 ACCESS -->
      <h3 class="mono-lg mb-2 flex items-center gap-2">
        <i data-lucide="key-round" style="width:18px;height:18px;" class="text-cyan"></i> ${t('api.section_access')}
      </h3>
      <p class="mono-sm text-muted mb-4">${t('api.access_desc')}</p>

      <div class="card card--transparent mb-6" style="padding:16px;">
        <div class="flex justify-between items-center mb-2">
          <span class="mono-xs text-muted fw-700">${t('api.examples_label')}</span>
          <button type="button" class="btn btn-ghost mono-xs" id="btn-copy-examples" style="padding:4px 10px;">
            <i data-lucide="copy" style="width:14px;height:14px;"></i> <span id="copy-status">${t('api.copy')}</span>
          </button>
        </div>
        <pre class="mono-sm" id="api-examples" style="background:var(--surface);border:1px solid var(--border);padding:12px;border-radius:4px;overflow-x:auto;margin:0;white-space:pre;">${examples.map(escapeHtml).join('\n')}</pre>
      </div>

      <!-- 02 DATA DOWNLOAD -->
      <h3 class="mono-lg mb-4 flex items-center gap-2">
        <i data-lucide="download" style="width:18px;height:18px;" class="text-cyan"></i> ${t('api.section_download')}
      </h3>

      <div class="card card--transparent mb-6" style="padding:16px;">
        <h4 class="mono-xs text-muted uppercase mb-2">${t('api.format_label')}</h4>
        <div class="flex gap-2 flex-wrap mb-4" id="export-format-buttons">
          ${FORMATS.map(f => `<button type="button" class="btn ${f === selectedFormat ? 'btn-cyan' : 'btn-ghost'} export-fmt-btn mono-sm" data-fmt="${f}" aria-pressed="${f === selectedFormat}">${f}</button>`).join('')}
        </div>

        <h4 class="mono-xs text-muted uppercase mb-2">${t('api.export_sector')}</h4>
        <div class="flex gap-2 flex-wrap mb-4" id="export-sector-buttons">
          ${SECTOR_IDS.map(id => `<button type="button" class="btn ${id === selectedSector ? 'btn-cyan' : 'btn-ghost'} export-sec-btn mono-sm" data-sec="${id}" aria-pressed="${id === selectedSector}">${escapeHtml(getSectorLabel(id))}</button>`).join('')}
        </div>

        <h4 class="mono-xs text-muted uppercase mb-2">
          ${t('api.export_region')} <span class="mono-xs text-muted fw-400">(${t('api.regions_official')})</span>
        </h4>
        <div class="region-container-box mb-6" style="background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:10px;max-height:150px;overflow-y:auto;box-shadow:inset 0 1px 3px rgba(0,0,0,0.03);">
          <div class="flex gap-2 flex-wrap" id="export-region-buttons">
            <button type="button" class="btn ${selectedRegion === 'all' ? 'btn-cyan' : 'btn-ghost'} export-reg-btn mono-sm" data-reg="all" aria-pressed="${selectedRegion === 'all'}" style="padding:4px 10px;font-size:12px;">${t('api.national')}</button>
          </div>
        </div>

        <h4 class="mono-xs text-muted uppercase mb-2">${t('api.filters_label')}</h4>
        <div class="flex gap-2 flex-wrap mb-6" id="active-filters-badges">
          <span class="mono-sm" style="background:var(--surface);padding:6px 12px;border:1px solid var(--border);border-radius:4px;" id="badge-sector"></span>
          <span class="mono-sm" style="background:var(--surface);padding:6px 12px;border:1px solid var(--border);border-radius:4px;" id="badge-region"></span>
        </div>

        <button class="btn btn-primary w-full justify-center mono-md fw-700" id="btn-generate-archive" style="padding:12px;">
          <i data-lucide="download-cloud" style="width:18px;height:18px;"></i> <span id="archive-label">${t('api.btn_archive')} (${selectedFormat})</span>
        </button>
      </div>

      <!-- 03 DOCUMENTATION -->
      <h3 class="mono-lg mb-4 flex items-center gap-2">
        <i data-lucide="book-open-check" style="width:18px;height:18px;" class="text-cyan"></i> ${t('api.section_docs')}
      </h3>

      <div class="flex flex-col gap-3 mb-6">
        ${docList.map(d => `
          <a class="card card--transparent doc-row" href="${escapeHtml(d.link)}" target="_blank" rel="noopener noreferrer" style="padding:16px;text-decoration:none;color:inherit;">
            <div class="flex items-center gap-4">
              <div class="source-icon" style="border:1px solid var(--border);">
                <i data-lucide="${escapeHtml(d.icon)}" style="width:18px;height:18px;"></i>
              </div>
              <div>
                <h5 class="mono-md fw-700">${escapeHtml(d.name)}</h5>
                <p class="mono-xs text-muted">${escapeHtml(d.desc)}</p>
              </div>
            </div>
            <span class="text-cyan mono-sm fw-700 flex items-center gap-1" style="font-size:13px;">
              ${t('common.open')} <i data-lucide="external-link" style="width:14px;height:14px;"></i>
            </span>
          </a>
        `).join('')}
      </div>

      <!-- Real limits (from /api/v1/health) -->
      <div class="card mb-6" style="padding:16px;border-color:var(--border-strong);background:var(--surface);">
        <div class="flex items-start gap-4">
          <i data-lucide="gauge" style="width:20px;height:20px;flex-shrink:0;" class="text-cyan"></i>
          <div>
            <h5 class="mono-md fw-700 mb-1" style="color:var(--text);">${t('api.rate_title')}</h5>
            <p class="mono-sm text-muted" id="api-limits-msg"><span class="skeleton" style="width:260px;"></span></p>
          </div>
        </div>
      </div>

      <!-- Real status + measured latency -->
      <div class="separator flex justify-between items-center" style="padding-top:16px;">
        <div>
          <div class="mono-xs fw-700 flex items-center gap-1" id="api-status-line"><span class="skeleton" style="width:160px;"></span></div>
          <div class="mono-xs" id="api-latency-line"></div>
        </div>
      </div>
    `;
  },

  async init() {
    renderBadges();

    document.querySelectorAll('.export-fmt-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        selectedFormat = e.currentTarget.getAttribute('data-fmt');
        setActive('.export-fmt-btn', e.currentTarget);
        const label = document.getElementById('archive-label');
        if (label) label.textContent = `${t('api.btn_archive')} (${selectedFormat})`;
      });
    });

    document.querySelectorAll('.export-sec-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        selectedSector = e.currentTarget.getAttribute('data-sec');
        setActive('.export-sec-btn', e.currentTarget);
        renderBadges();
      });
    });

    wireRegionButtons();
    loadRegions();

    document.getElementById('btn-generate-archive')?.addEventListener('click', downloadExport);

    document.getElementById('btn-copy-examples')?.addEventListener('click', async () => {
      const text = document.getElementById('api-examples')?.textContent || '';
      const status = document.getElementById('copy-status');
      try {
        await navigator.clipboard.writeText(text);
        if (status) { status.textContent = t('common.copied'); setTimeout(() => { status.textContent = t('api.copy'); }, 2000); }
      } catch (_) {
        showToast(t('api.copy_failed'), 'error');
      }
    });

    // Real health: status, measured round-trip latency, limits, supported formats.
    const t0 = performance.now();
    const health = await fetchHealth();
    const latency = Math.round(performance.now() - t0);

    const statusEl = document.getElementById('api-status-line');
    const latEl = document.getElementById('api-latency-line');
    const limitsEl = document.getElementById('api-limits-msg');

    if (statusEl) {
      statusEl.className = `mono-xs fw-700 flex items-center gap-1 ${health ? 'text-green' : 'text-accent'}`;
      statusEl.textContent = health ? t('api.api_ok') : t('api.api_down');
    }
    if (latEl) latEl.textContent = health ? `${t('api.latency')}: ${latency} ms` : '';
    if (limitsEl) {
      const l = health && health.limits;
      limitsEl.textContent = l
        ? t('api.limits_msg').replace('{a}', l.analysis_per_hour)
        : t('api.limits_unknown');
    }

    // Offer Parquet only if the server can actually produce it.
    if (health && health.exports && health.exports.parquet === false) {
      document.querySelector('.export-fmt-btn[data-fmt="PARQUET"]')?.remove();
      if (selectedFormat === 'PARQUET') {
        selectedFormat = 'JSON';
        const jsonBtn = document.querySelector('.export-fmt-btn[data-fmt="JSON"]');
        if (jsonBtn) setActive('.export-fmt-btn', jsonBtn);
        const label = document.getElementById('archive-label');
        if (label) label.textContent = `${t('api.btn_archive')} (${selectedFormat})`;
      }
    }
  },
};
