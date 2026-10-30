/**
 * FreeData.td — Chart Factory
 *
 * Chart.js is loaded ON DEMAND (only pages that draw a chart pay for it) and
 * its absence is never fatal: if the CDN is blocked/offline the chart area
 * shows a message instead of the whole SPA crashing at import time.
 *
 * No chart ever invents data: with nothing to plot, an explicit empty state is
 * shown (previous versions drew made-up demo series).
 */

import { t } from './i18n.js';

const CHART_JS_SRC = '/static/vendor/chart-4.4.7.umd.js';
const chartInstances = {};
let _chartLibPromise = null;

export function loadChartLib() {
  if (window.Chart) return Promise.resolve(window.Chart);
  if (!_chartLibPromise) {
    _chartLibPromise = new Promise((resolve, reject) => {
      const s = document.createElement('script');
      s.src = CHART_JS_SRC;
      s.async = true;
      s.onload = () => {
        if (window.Chart) {
          window.Chart.defaults.color = '#6c757d';
          window.Chart.defaults.font.family = "'Roboto Mono', monospace";
          resolve(window.Chart);
        } else {
          _chartLibPromise = null;
          reject(new Error('Chart.js loaded but global missing'));
        }
      };
      s.onerror = () => {
        _chartLibPromise = null; // allow a later retry
        reject(new Error('Chart.js could not be loaded'));
      };
      document.head.appendChild(s);
    });
  }
  return _chartLibPromise;
}

function destroyIfExists(key) {
  if (chartInstances[key]) {
    chartInstances[key].destroy();
    delete chartInstances[key];
  }
}

/** Destroy every live chart (called by the router before each view change,
 *  so detached canvases don't keep Chart instances alive). */
export function destroyAllCharts() {
  Object.keys(chartInstances).forEach(destroyIfExists);
}

function showMessage(canvas, text) {
  canvas.style.display = 'none';
  let msg = canvas.parentElement.querySelector('.chart-empty');
  if (!msg) {
    msg = document.createElement('div');
    msg.className = 'chart-empty mono-xs text-muted';
    msg.setAttribute('role', 'status');
    canvas.parentElement.appendChild(msg);
  }
  msg.textContent = text;
}

function clearMessage(canvas) {
  canvas.style.display = '';
  const msg = canvas.parentElement.querySelector('.chart-empty');
  if (msg) msg.remove();
}

/** Shared bootstrap: resolve canvas, handle empty data and a missing library. */
async function draw(key, canvasId, hasData, build) {
  destroyIfExists(key);
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;

  if (!hasData) {
    showMessage(canvas, t('common.no_chart_data'));
    return;
  }

  let Chart;
  try {
    Chart = await loadChartLib();
  } catch (err) {
    console.warn(err.message);
    showMessage(canvas, t('common.chart_unavailable'));
    return;
  }

  // The view may have changed while the library was loading.
  const live = document.getElementById(canvasId);
  if (!live || live !== canvas) return;
  destroyIfExists(key);
  clearMessage(canvas);
  chartInstances[key] = new Chart(canvas, build());
}

/** Replace a chart by an explanatory message (never an invented or lonely-dot chart). */
export function showChartMessage(canvasId, text, key = 'mais') {
  destroyIfExists(key);
  const canvas = document.getElementById(canvasId);
  if (canvas) showMessage(canvas, text);
}

/* ── Indicator trend (line) ── expects rows already filtered to ONE indicator. */
export async function initChartMais(rows = null) {
  const data = Array.isArray(rows) ? rows.filter(r => r && r.value !== null && r.value !== undefined && !isNaN(Number(r.value))) : [];
  // Oldest → newest so the line reads left to right.
  const ordered = [...data].sort((a, b) =>
    String(a.reference_date || a.collected_at || '').localeCompare(String(b.reference_date || b.collected_at || '')));
  const labels = ordered.map((r, i) => String(r.reference_date || r.collected_at || `#${i + 1}`).substring(0, 10));
  const values = ordered.map(r => Number(r.value));

  await draw('mais', 'chart-mais', values.length > 0, () => ({
    type: 'line',
    data: {
      labels,
      datasets: [{
        data: values,
        borderColor: '#2563eb',
        borderWidth: 2,
        tension: 0.3,
        pointBackgroundColor: '#2563eb',
        pointRadius: 3,
        fill: false,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { grid: { color: '#f1f3f5' } },
        y: { grid: { color: '#f1f3f5' } },
      },
    },
  }));
}

/* ── Data density by region (bar) ── expects { regionName: { total, validated } } */
export async function initChartDensity(density = null) {
  const labels = density && typeof density === 'object' ? Object.keys(density) : [];
  const totals = labels.map(k => Number((typeof density[k] === 'object' ? density[k].total : density[k]) || 0));

  // Region names never fit under 23 vertical bars on a phone (they overlapped): draw
  // horizontal bars and give the chart a height proportional to the number of regions.
  const box = document.getElementById('chart-density');
  if (box && box.parentElement && labels.length) box.parentElement.style.height = `${Math.max(150, labels.length * 26 + 30)}px`;

  await draw('density', 'chart-density', labels.length > 0, () => ({
    type: 'bar',
    data: {
      labels,
      datasets: [{
        label: t('insights.density_series'),
        data: totals,
        backgroundColor: '#2563eb',
        barPercentage: 0.8,
        categoryPercentage: 0.8,
      }],
    },
    options: {
      indexAxis: 'y',
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        y: { grid: { display: false }, ticks: { autoSkip: false, font: { size: 11 } } },
        x: { grid: { color: '#f1f3f5' }, beginAtZero: true, ticks: { precision: 0 } },
      },
    },
  }));
}

/* ── System load (line) ── only drawn from REAL measurements ({labels, values}). */
export async function initChartLoad(load = null) {
  const values = load && Array.isArray(load.values) ? load.values : [];
  const labels = load && Array.isArray(load.labels) ? load.labels : values.map((_, i) => `#${i + 1}`);

  await draw('load', 'chart-load', values.length > 0, () => ({
    type: 'line',
    data: {
      labels,
      datasets: [{
        data: values,
        borderColor: '#0284c7',
        borderWidth: 2,
        tension: 0.3,
        pointBackgroundColor: '#0284c7',
        pointRadius: 3,
        fill: false,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { grid: { color: '#f1f3f5' } },
        y: { grid: { color: '#f1f3f5' }, beginAtZero: true },
      },
    },
  }));
}
