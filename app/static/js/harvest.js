/**
 * Shared live-collection runner used by the home and repository pages.
 *
 * Runs sectors ONE AT A TIME (parallel runs spiked server memory and burned the hourly
 * quota in a single click), stops at the first HTTP 429, and reports what really happened.
 */

import { triggerHarvest } from './api_client.js';

// Sectors collectable without the admin key.
export const PUBLIC_HARVEST_SECTORS = ['agriculture', 'environment', 'markets', 'economy', 'health', 'energy'];

export function isPublicHarvestSector(sector) {
  return PUBLIC_HARVEST_SECTORS.includes(sector);
}

/**
 * @param {string[]} sectors
 * @param {(i:number, n:number, sector:string)=>void} [onProgress]
 * @returns {Promise<{ok:number, n:number, stored:number, rateLimited:boolean}>}
 */
export async function runHarvest(sectors, onProgress) {
  const n = sectors.length;
  let ok = 0;
  let stored = 0;
  let rateLimited = false;

  for (let i = 0; i < n; i++) {
    if (onProgress) onProgress(i + 1, n, sectors[i]);
    try {
      const res = await triggerHarvest(sectors[i], 'all');
      ok += 1;
      stored += Number(res && res.stored) || 0;
    } catch (err) {
      console.warn(`harvest ${sectors[i]} failed:`, err);
      if (err && err.status === 429) { rateLimited = true; break; }
    }
  }
  return { ok, n, stored, rateLimited };
}
