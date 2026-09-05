/**
 * FreeData.td — Chart Factory
 *
 * Centralised Chart.js configuration and lazy-initialisation helpers.
 * Handles dynamic data rendering and light mode colors.
 */

// Global Chart.js defaults (Light Mode)
Chart.defaults.color = '#6c757d';
Chart.defaults.font.family = "'Roboto Mono', monospace";

const chartInstances = {};

function destroyIfExists(key) {
  if (chartInstances[key]) {
    chartInstances[key].destroy();
    delete chartInstances[key];
  }
}

/* ── Indicator Price Trend (Line Chart) ── */
export function initChartMais(dynamicData = null) {
  destroyIfExists('mais');
  const ctx = document.getElementById('chart-mais');
  if (!ctx) return;

  let labels = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN'];
  let values = [15000, 15500, 15200, 16000, 16500, 16400];

  if (Array.isArray(dynamicData) && dynamicData.length >= 1) {
    labels = dynamicData.map((item, idx) => {
      const d = item.reference_date || item.collected_at || '';
      return d ? d.substring(5, 10) : `P${idx + 1}`;
    }).reverse();
    values = dynamicData.map(item => Number(item.value) || 0).reverse();
  }

  chartInstances['mais'] = new Chart(ctx, {
    type: 'line',
    data: {
      labels: labels,
      datasets: [{
        data: values,
        borderColor: '#ff4500',
        borderWidth: 2,
        tension: 0.3,
        pointBackgroundColor: '#ff4500',
        pointRadius: 3,
        fill: false,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { grid: { color: '#f1f3f5' } },
        y: { grid: { color: '#f1f3f5' } },
      }
    }
  });
}

/* ── Data Density by Region (Bar Chart) ── */
export function initChartDensity(dynamicDensity = null) {
  destroyIfExists('density');
  const ctx = document.getElementById('chart-density');
  if (!ctx) return;

  let labels = ['ABÉ', 'MAO', 'N\'D', 'MOU', 'SAR', 'FAY'];
  let rawCounts = [20, 45, 33, 27, 12, 19];
  let validatedCounts = [35, 45, 85, 90, 75, 0];

  if (dynamicDensity && typeof dynamicDensity === 'object') {
    labels = Object.keys(dynamicDensity).slice(0, 7);
    rawCounts = labels.map(k => (typeof dynamicDensity[k] === 'object' ? dynamicDensity[k].total : dynamicDensity[k]) || 0);
    validatedCounts = labels.map(k => (typeof dynamicDensity[k] === 'object' ? dynamicDensity[k].validated : dynamicDensity[k]) || 0);
  }

  chartInstances['density'] = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: labels,
      datasets: [
        { label: 'Brut / Raw', data: rawCounts, backgroundColor: '#ff4500', barPercentage: 0.8, categoryPercentage: 0.4 },
        { label: 'Validé / Clean', data: validatedCounts, backgroundColor: '#0284c7', barPercentage: 0.8, categoryPercentage: 0.4 },
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { grid: { display: false } },
        y: { grid: { color: '#f1f3f5' } },
      }
    }
  });
}

/* ── System Load 24H (Line Chart) ── */
export function initChartLoad() {
  destroyIfExists('load');
  const ctx = document.getElementById('chart-load');
  if (!ctx) return;
  chartInstances['load'] = new Chart(ctx, {
    type: 'line',
    data: {
      labels: ['00:00', '04:00', '08:00', '12:00', '16:00', '20:00', '24:00'],
      datasets: [{
        data: [30, 40, 35, 55, 65, 60, 75],
        borderColor: '#0284c7',
        borderWidth: 2,
        tension: 0.3,
        pointBackgroundColor: '#0284c7',
        pointRadius: 3,
        fill: false,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { grid: { color: '#f1f3f5' } },
        y: { grid: { color: '#f1f3f5' }, min: 0, max: 100 },
      }
    }
  });
}
