/**
 * View: Crop suitability.
 * Pick a crop (or "all") and a region; the server compares the crop's FAO EcoCrop needs with the region's
 * rainy-season climate (NASA POWER) and soil (SoilGrids). Everything shown comes from the API answer.
 * The URL keeps the choice (#/crops?region=...&crop=...) without re-rendering the page.
 */

import { fetchCrops, fetchSuitability } from '../api_client.js';
import { buildHash } from '../router.js';
import { getLang, t } from '../i18n.js';
import { escapeHtml } from '../sanitize.js';

const FACTOR_ORDER = ['rain_mm', 'temp_mean_c', 'season_days', 'ph'];
let _catalog = null;
let _token = 0; // a slow answer must never overwrite a newer one

const pct = (x) => `${Math.round((x || 0) * 100)} %`;
const cropName = (c) => (getLang() === 'en' ? c.name_en : c.name_fr);
const num = (v) => (Number.isInteger(v) ? String(v) : String(Math.round(v * 10) / 10));

function verdictBadge(verdict) {
  return `<span class="crop-verdict crop-verdict--${escapeHtml(verdict)}">${escapeHtml(t(`crops.verdict.${verdict}`))}</span>`;
}

function bar(score) {
  return `<span class="crop-bar" aria-hidden="true"><span class="crop-bar-fill" style="width:${Math.round((score || 0) * 100)}%"></span></span>`;
}

function requirementText(factor, req) {
  const unit = t(`crops.unit.${factor}`);
  const u = unit ? ` ${unit}` : '';
  if (factor === 'season_days') return `${t('crops.needs')} : ${num(req.cycle_days[0])}${u}`;
  const [lo, a, b, hi] = req[factor];
  return `${t('crops.optimum')} ${num(a)}–${num(b)}${u} · ${t('crops.tolerated')} ${num(lo)}–${num(hi)}${u}`;
}

function factorRows(result) {
  return FACTOR_ORDER.filter(f => result.factors[f]).map(f => {
    const fa = result.factors[f];
    const limiting = result.limiting === f;
    const unit = t(`crops.unit.${f}`);
    return `<li class="crop-factor${limiting ? ' is-limiting' : ''}">
      <div class="crop-factor-head">
        <span class="crop-factor-name">${escapeHtml(t(`crops.factor.${f}`))}${limiting ? ` <span class="badge badge--muted mono-xs">${escapeHtml(t('crops.limiting'))}</span>` : ''}</span>
        <span class="crop-factor-value mono-xs">${escapeHtml(num(fa.value))}${unit ? ` ${escapeHtml(unit)}` : ''} · ${escapeHtml(pct(fa.score))}</span>
      </div>
      ${bar(fa.score)}
      <div class="crop-factor-req mono-xs text-muted">${escapeHtml(requirementText(f, result.requirements))}</div>
    </li>`;
  }).join('');
}

function seasonLine(site) {
  if (!site || !site.wet_months) return '';
  const text = site.wet_months.length
    ? t('crops.season_value').replace('{months}', site.wet_months.length).replace('{rain}', num(site.rain_mm)).replace('{temp}', num(site.temp_mean_c))
    : t('crops.none_season');
  return `<p class="crop-season mono-xs text-muted"><strong>${escapeHtml(t('crops.season'))}</strong> · ${escapeHtml(text)}</p>`;
}

function irrigationNote(r) {
  const w = r.if_irrigated;
  if (!w) return '';
  const text = t('crops.irrigated_hint').replace('{score}', pct(w.score)).replace('{verdict}', t(`crops.verdict.${w.verdict}`).toLowerCase());
  return `<p class="crop-irrigated" id="crop-irrigated">${escapeHtml(text)}</p>`;
}

function detailHtml(data) {
  const r = data.results[0];
  return `<div class="card crop-result" id="crop-result">
    <div class="crop-result-head">
      <div>
        <h3 class="crop-result-title">${escapeHtml(cropName(r))}</h3>
        <div class="mono-xs text-muted">${escapeHtml(data.region)}</div>
      </div>
      <div class="crop-score" aria-label="${escapeHtml(t('crops.score'))}">
        ${verdictBadge(r.verdict)}
        <span class="crop-score-num">${escapeHtml(pct(r.score))}</span>
      </div>
    </div>
    ${seasonLine(data.site)}
    <ul class="crop-factors">${factorRows(r)}</ul>
    ${irrigationNote(r)}
    <p class="crop-note mono-xs text-muted">${escapeHtml(t('crops.soil_note'))}</p>
  </div>`;
}

function rankingHtml(data) {
  const rows = data.results.map(r => `<li>
      <button type="button" class="crop-rank-row" data-crop="${escapeHtml(r.crop)}" aria-label="${escapeHtml(`${cropName(r)} — ${t('crops.open_crop')}`)}">
        <span class="crop-rank-name">${escapeHtml(cropName(r))}</span>
        ${bar(r.score)}
        <span class="crop-rank-score mono-xs">${escapeHtml(pct(r.score))}</span>
        ${verdictBadge(r.verdict)}${r.if_irrigated ? `<span class="badge badge--muted mono-xs" title="${escapeHtml(t('crops.irrigated_badge_title'))}">${escapeHtml(t('crops.irrigated_badge'))} ${escapeHtml(pct(r.if_irrigated.score))}</span>` : ''}
      </button>
    </li>`).join('');
  return `<div class="card crop-result" id="crop-result">
    <h3 class="crop-result-title">${escapeHtml(t('crops.ranking'))}</h3>
    <div class="mono-xs text-muted">${escapeHtml(data.region)}</div>
    ${seasonLine(data.site)}
    <ul class="crop-rank">${rows}</ul>
  </div>`;
}

async function refresh() {
  const region = document.getElementById('crop-region')?.value;
  const crop = document.getElementById('crop-crop')?.value || '';
  const out = document.getElementById('crop-output');
  if (!region || !out) return;
  const token = ++_token;
  window.history.replaceState(null, '', buildHash('crops', { region, crop }));
  out.innerHTML = `<p class="mono-xs text-muted" role="status">${escapeHtml(t('crops.loading'))}</p>`;
  try {
    const data = await fetchSuitability(region, crop || null);
    if (token !== _token) return;
    out.innerHTML = crop ? detailHtml(data) : rankingHtml(data);
    out.querySelectorAll('.crop-rank-row').forEach(btn => btn.addEventListener('click', () => {
      document.getElementById('crop-crop').value = btn.dataset.crop;
      refresh();
    }));
  } catch (err) {
    if (token !== _token) return;
    out.innerHTML = `<div class="alert alert--danger" role="alert"><strong>${escapeHtml(t('crops.error'))}</strong> ${escapeHtml(err && err.message ? err.message : '')}</div>`;
  }
}

export const CropsView = {
  render() {
    return `<section class="crops-view">
      <header class="crops-head">
        <h2 class="hero-title">${escapeHtml(t('crops.title'))}</h2>
        <p class="crops-sub">${escapeHtml(t('crops.subtitle'))}</p>
      </header>
      <div class="crops-controls">
        <label class="crops-field"><span class="mono-xs">${escapeHtml(t('crops.crop_label'))}</span>
          <select id="crop-crop" class="input-search"></select></label>
        <label class="crops-field"><span class="mono-xs">${escapeHtml(t('crops.region_label'))}</span>
          <select id="crop-region" class="input-search"></select></label>
      </div>
      <div id="crop-output" aria-live="polite"></div>
      <aside class="card crops-method">
        <h3>${escapeHtml(t('crops.method_title'))}</h3>
        <p>${escapeHtml(t('crops.method_body'))}</p>
        <p class="mono-xs text-muted">${escapeHtml(t('crops.caveat'))}</p>
        <p class="mono-xs text-muted">${escapeHtml(t('crops.sources'))}</p>
      </aside>
    </section>`;
  },

  async init(params = {}) {
    const out = document.getElementById('crop-output');
    _catalog = await fetchCrops();
    if (!_catalog || !_catalog.regions || !_catalog.regions.length) {
      out.innerHTML = `<div class="alert alert--danger" role="alert">${escapeHtml(t('crops.no_data'))}</div>`;
      return;
    }
    const lang = getLang();
    const cropSel = document.getElementById('crop-crop');
    cropSel.innerHTML = `<option value="">${escapeHtml(t('crops.all_crops'))}</option>`
      + _catalog.crops.map(c => `<option value="${escapeHtml(c.id)}">${escapeHtml(lang === 'en' ? c.name_en : c.name_fr)}</option>`).join('');
    const regionSel = document.getElementById('crop-region');
    regionSel.innerHTML = _catalog.regions.map(r => `<option value="${escapeHtml(r)}">${escapeHtml(r)}</option>`).join('');
    if (params.crop && _catalog.crops.some(c => c.id === params.crop)) cropSel.value = params.crop;
    if (params.region && _catalog.regions.includes(params.region)) regionSel.value = params.region;
    cropSel.addEventListener('change', refresh);
    regionSel.addEventListener('change', refresh);
    await refresh();
  },
};
