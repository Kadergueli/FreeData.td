/**
 * FreeData.td — API Client Module
 *
 * Interfaces with FastAPI endpoints for real-time data fetching,
 * automated collection triggers, AI study generation, and data exports.
 */

const BASE_URL = '/api/v1';

export async function fetchHealth() {
  try {
    const res = await fetch(`${BASE_URL}/health`);
    if (!res.ok) throw new Error(`HTTP error ${res.status}`);
    return await res.json();
  } catch (err) {
    console.warn('fetchHealth error:', err);
    return null;
  }
}

export async function fetchObservations(sector = null, limit = 100) {
  try {
    let url = `${BASE_URL}/observations?limit=${limit}`;
    if (sector && sector.toLowerCase() !== 'all' && sector.toLowerCase() !== 'tous') {
      url += `&sector=${encodeURIComponent(sector.toLowerCase())}`;
    }
    const res = await fetch(url);
    if (!res.ok) throw new Error(`HTTP error ${res.status}`);
    return await res.json();
  } catch (err) {
    console.warn('fetchObservations error:', err);
    return [];
  }
}

export async function fetchCatalog() {
  try {
    const res = await fetch(`${BASE_URL}/catalog`);
    if (!res.ok) throw new Error(`HTTP error ${res.status}`);
    return await res.json();
  } catch (err) {
    console.warn('fetchCatalog error:', err);
    return [];
  }
}

export async function fetchAudit() {
  try {
    const res = await fetch(`${BASE_URL}/pipeline/audit`);
    if (!res.ok) throw new Error(`HTTP error ${res.status}`);
    return await res.json();
  } catch (err) {
    console.warn('fetchAudit error:', err);
    return null;
  }
}

export async function triggerAgricultureHarvest(source = 'all') {
  try {
    const res = await fetch(`${BASE_URL}/collection/agriculture?source=${encodeURIComponent(source)}`, {
      method: 'POST',
    });
    if (!res.ok) throw new Error(`HTTP error ${res.status}`);
    return await res.json();
  } catch (err) {
    console.error('triggerAgricultureHarvest error:', err);
    throw err;
  }
}

export async function triggerEnvironmentHarvest(source = 'all') {
  try {
    const res = await fetch(`${BASE_URL}/collection/environment?source=${encodeURIComponent(source)}`, {
      method: 'POST',
    });
    if (!res.ok) throw new Error(`HTTP error ${res.status}`);
    return await res.json();
  } catch (err) {
    console.error('triggerEnvironmentHarvest error:', err);
    throw err;
  }
}

export async function triggerMarketsHarvest(source = 'all') {
  try {
    const res = await fetch(`${BASE_URL}/collection/markets?source=${encodeURIComponent(source)}`, {
      method: 'POST',
    });
    if (!res.ok) throw new Error(`HTTP error ${res.status}`);
    return await res.json();
  } catch (err) {
    console.error('triggerMarketsHarvest error:', err);
    throw err;
  }
}

export async function triggerEconomyHarvest(source = 'all') {
  try {
    const res = await fetch(`${BASE_URL}/collection/economy?source=${encodeURIComponent(source)}`, {
      method: 'POST',
    });
    if (!res.ok) throw new Error(`HTTP error ${res.status}`);
    return await res.json();
  } catch (err) {
    console.error('triggerEconomyHarvest error:', err);
    throw err;
  }
}

export async function triggerTransportHarvest(source = 'all') {
  try {
    const res = await fetch(`${BASE_URL}/collection/transport?source=${encodeURIComponent(source)}`, {
      method: 'POST',
    });
    if (!res.ok) throw new Error(`HTTP error ${res.status}`);
    return await res.json();
  } catch (err) {
    console.error('triggerTransportHarvest error:', err);
    throw err;
  }
}

export async function triggerEducationHarvest(source = 'all') {
  try {
    const res = await fetch(`${BASE_URL}/collection/education?source=${encodeURIComponent(source)}`, {
      method: 'POST',
    });
    if (!res.ok) throw new Error(`HTTP error ${res.status}`);
    return await res.json();
  } catch (err) {
    console.error('triggerEducationHarvest error:', err);
    throw err;
  }
}

export async function generateStudy(sector = null) {
  try {
    let url = `${BASE_URL}/studies`;
    if (sector && sector.toLowerCase() !== 'all') {
      url += `?sector=${encodeURIComponent(sector.toLowerCase())}`;
    }
    const res = await fetch(url, { method: 'POST' });
    if (!res.ok) {
      const errJson = await res.json().catch(() => ({}));
      throw new Error(errJson.detail || `HTTP error ${res.status}`);
    }
    return await res.json();
  } catch (err) {
    console.error('generateStudy error:', err);
    throw err;
  }
}

export function getExportUrl(format = 'csv', sector = null) {
  let url = `${BASE_URL}/export/${format.toLowerCase()}`;
  if (sector && sector.toLowerCase() !== 'all') {
    url += `?sector=${encodeURIComponent(sector.toLowerCase())}`;
  }
  return url;
}
