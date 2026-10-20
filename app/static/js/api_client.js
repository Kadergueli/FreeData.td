/**
 * FreeData.td — API Client Module
 *
 * Interfaces with FastAPI endpoints for real-time data fetching,
 * automated collection triggers, AI study generation, and data exports.
 *
 * Every request has a timeout (a hung connection used to leave the UI on its
 * loading state forever) and surfaces the server's own error message.
 */

const BASE_URL = '/api/v1';
const DEFAULT_TIMEOUT_MS = 30000;
const SLOW_TIMEOUT_MS = 150000; // LLM report generation, live harvests

async function requestJson(url, { method = 'GET', timeout = DEFAULT_TIMEOUT_MS } = {}) {
  const init = { method };
  if (typeof AbortSignal !== 'undefined' && typeof AbortSignal.timeout === 'function') {
    init.signal = AbortSignal.timeout(timeout);
  }
  let res;
  try {
    res = await fetch(url, init);
  } catch (err) {
    if (err && (err.name === 'TimeoutError' || err.name === 'AbortError')) {
      const e = new Error('Request timed out');
      e.status = 0;
      throw e;
    }
    throw err;
  }
  if (!res.ok) {
    let detail = '';
    try { detail = (await res.json()).detail; } catch (_) { /* non-JSON error body */ }
    const e = new Error(typeof detail === 'string' && detail ? detail : `HTTP error ${res.status}`);
    e.status = res.status;
    throw e;
  }
  return res.json();
}

export async function fetchHealth() {
  try {
    return await requestJson(`${BASE_URL}/health`);
  } catch (err) {
    console.warn('fetchHealth error:', err);
    return null;
  }
}

/** opts: { q: free-text search (server-side), region } */
export async function fetchObservations(sector = null, limit = 100, opts = {}) {
  try {
    const params = new URLSearchParams({ limit: String(limit) });
    if (sector && sector.toLowerCase() !== 'all' && sector.toLowerCase() !== 'tous') {
      params.set('sector', sector.toLowerCase());
    }
    if (opts.q && opts.q.trim()) params.set('q', opts.q.trim().slice(0, 100));
    if (opts.region && opts.region.toLowerCase() !== 'all') params.set('region', opts.region);
    return await requestJson(`${BASE_URL}/observations?${params}`);
  } catch (err) {
    console.warn('fetchObservations error:', err);
    return [];
  }
}

export async function fetchStats() {
  try {
    return await requestJson(`${BASE_URL}/stats`);
  } catch (err) {
    console.warn('fetchStats error:', err);
    return null;
  }
}

export async function fetchCatalog() {
  try {
    return await requestJson(`${BASE_URL}/catalog`);
  } catch (err) {
    console.warn('fetchCatalog error:', err);
    return [];
  }
}

export async function fetchAudit() {
  try {
    return await requestJson(`${BASE_URL}/pipeline/audit`);
  } catch (err) {
    console.warn('fetchAudit error:', err);
    return null;
  }
}

/** Trigger a live collection for one sector. Throws Error with .status
 *  (429 = rate limited, 401/403 = admin-only sector, 503 = backend unavailable). */
export async function triggerHarvest(sector, source = 'all') {
  return requestJson(
    `${BASE_URL}/collection/${encodeURIComponent(sector)}?source=${encodeURIComponent(source)}`,
    { method: 'POST', timeout: SLOW_TIMEOUT_MS },
  );
}

// Per-sector wrappers kept for existing imports.
export const triggerAgricultureHarvest = (source = 'all') => triggerHarvest('agriculture', source);
export const triggerEnvironmentHarvest = (source = 'all') => triggerHarvest('environment', source);
export const triggerMarketsHarvest = (source = 'all') => triggerHarvest('markets', source);
export const triggerEconomyHarvest = (source = 'all') => triggerHarvest('economy', source);
export const triggerHealthHarvest = (source = 'all') => triggerHarvest('health', source);
export const triggerEnergyHarvest = (source = 'all') => triggerHarvest('energy', source);
export const triggerTransportHarvest = (source = 'all') => triggerHarvest('transport', source);
export const triggerEducationHarvest = (source = 'all') => triggerHarvest('education', source);

export async function fetchStudies(sector = null, limit = 100) {
  try {
    const params = new URLSearchParams({ limit: String(limit) });
    if (sector && sector.toLowerCase() !== 'all') params.set('sector', sector.toLowerCase());
    const data = await requestJson(`${BASE_URL}/studies?${params}`);
    return data.studies || [];
  } catch (err) {
    console.error('fetchStudies error:', err);
    return [];
  }
}

export async function generateStudy(sector = null) {
  let url = `${BASE_URL}/studies`;
  if (sector && sector.toLowerCase() !== 'all') {
    url += `?sector=${encodeURIComponent(sector.toLowerCase())}`;
  }
  try {
    return await requestJson(url, { method: 'POST', timeout: SLOW_TIMEOUT_MS });
  } catch (err) {
    console.error('generateStudy error:', err);
    throw err;
  }
}

export function getExportUrl(format = 'csv', sector = null, region = null) {
  let url = `${BASE_URL}/export/${format.toLowerCase()}`;
  const params = [];
  if (sector && sector.toLowerCase() !== 'all') {
    params.push(`sector=${encodeURIComponent(sector.toLowerCase())}`);
  }
  if (region && region.toLowerCase() !== 'all') {
    params.push(`region=${encodeURIComponent(region)}`);
  }
  if (params.length) url += `?${params.join('&')}`;
  return url;
}

export async function fetchRegions() {
  try {
    return await requestJson(`${BASE_URL}/regions`);
  } catch (err) {
    console.error('fetchRegions error:', err);
    return [];
  }
}

export async function fetchCrossSector() {
  try {
    return await requestJson(`${BASE_URL}/insights/cross-sector`);
  } catch (err) {
    console.warn('fetchCrossSector error:', err);
    return null;
  }
}
