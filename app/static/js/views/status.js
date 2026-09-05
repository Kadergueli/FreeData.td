/**
 * View: Infrastructure Status — System Monitor (DATABASE LIVE AUDIT)
 */

import { fetchHealth, fetchAudit } from '../api_client.js';
import { initChartLoad } from '../charts.js';
import { t } from '../i18n.js';

export const StatusView = {
  render() {
    return `
      <div class="flex justify-between items-start mb-6">
        <div>
          <div class="mono-xs text-muted fw-700 mb-1 flex items-center gap-1">
            <i data-lucide="activity" style="width:14px;height:14px;"></i> SURVEILLANCE INFRASTRUCTURE
          </div>
          <h2 class="hero-title uppercase text-accent" style="font-size:24px;">${t('status.title')}</h2>
        </div>
        <div class="mono-xs text-muted flex items-center gap-1" id="status-storage-backend">
          <i data-lucide="database" style="width:12px;height:12px;"></i> STOCKAGE : ${t('common.loading')}
        </div>
      </div>

      <div class="grid-2 mb-6">
        <div class="card" style="padding:16px;">
          <h4 class="mono-xs text-muted uppercase mb-2">${t('home.stat_score')}</h4>
          <div class="mono-2xl fw-700 mb-1" id="status-val-score">...</div>
          <div class="mono-xs text-green fw-700 flex items-center gap-1" id="status-val-trend">
            <i data-lucide="shield-check" style="width:14px;height:14px;"></i> AUDIT DE L'INFRASTRUCTURE
          </div>
        </div>
        <div class="card" style="padding:16px;">
          <h4 class="mono-xs text-muted uppercase mb-2">${t('home.stat_obs')}</h4>
          <div class="mono-2xl fw-700 mb-1" id="status-total-obs">...</div>
          <div class="mono-xs text-accent fw-700 flex items-center gap-1" id="status-anomalies-count">
            <i data-lucide="check-circle" style="width:14px;height:14px;"></i> ANOMALIES : 0
          </div>
        </div>
      </div>

      <h4 class="uppercase mb-4 flex items-center gap-2" style="font-size:14px;">
        <i data-lucide="git-branch" style="width:16px;height:16px;" class="text-cyan"></i> ${t('status.pipelines_title')} (Base en Direct)
      </h4>

      <div class="flex flex-col gap-3 mb-6" id="pipeline-cards-container">
        <div class="card pipeline-card">
          <div class="flex justify-between items-start mb-2">
            <h5 class="uppercase flex items-center gap-2" style="font-size:14px;">
              <i data-lucide="table" style="width:14px;height:14px;"></i> Table Brute (Raw)
            </h5>
            <span class="mono-sm fw-700" id="raw-count-tag">...</span>
          </div>
          <p class="mono-xs text-muted">Données brutes capturées automatiquement par les agents de collecte.</p>
        </div>

        <div class="card pipeline-card">
          <div class="flex justify-between items-start mb-2">
            <h5 class="uppercase flex items-center gap-2" style="font-size:14px;">
              <i data-lucide="check-square" style="width:14px;height:14px;"></i> Table Nettoyée (Clean)
            </h5>
            <span class="mono-sm fw-700" id="clean-count-tag">...</span>
          </div>
          <p class="mono-xs text-muted">Observations normalisées et validées par le moteur Data Science (10 règles).</p>
        </div>

        <div class="card pipeline-card">
          <div class="flex justify-between items-start mb-2">
            <h5 class="uppercase flex items-center gap-2" style="font-size:14px;">
              <i data-lucide="globe" style="width:14px;height:14px;"></i> Table Publique (Public)
            </h5>
            <span class="mono-sm fw-700" id="public-count-tag">...</span>
          </div>
          <p class="mono-xs text-muted">Données publiques prêtes pour l'exportation et les requêtes API.</p>
        </div>
      </div>

      <!-- Audit Logs Live -->
      <div class="card mb-6" style="padding:16px;border-color:var(--border-strong);">
        <h4 class="mono-sm uppercase mb-4 text-cyan flex items-center gap-2">
          <i data-lucide="list-checks" style="width:16px;height:16px;"></i> Derniers Journaux d'Audit en Base
        </h4>
        <div class="flex flex-col gap-2" id="audit-logs-list" style="max-height:220px;overflow-y:auto;">
          <p class="mono-xs text-muted">${t('common.loading')}</p>
        </div>
      </div>

      <!-- Load Chart -->
      <div class="card mb-6" style="padding:16px;border-color:var(--border-strong);">
        <h4 class="mono-sm uppercase mb-4 flex items-center gap-2">
          <i data-lucide="cpu" style="width:16px;height:16px;"></i> ${t('status.load_title')} (24H)
        </h4>
        <div class="chart-container" style="height:150px;">
          <canvas id="chart-load"></canvas>
        </div>
        <div class="separator flex justify-between items-center mt-4">
          <span class="mono-xs text-muted">Charge Maximale : Optimale</span>
          <span class="mono-xs text-muted flex items-center gap-1" id="status-scheduler-label">
            <i data-lucide="clock" style="width:12px;height:12px;"></i> ${t('status.scheduler_label')} : Actif
          </span>
        </div>
      </div>
    `;
  },

  async init() {
    if (window.lucide) window.lucide.createIcons();
    initChartLoad();

    try {
      const [health, audit] = await Promise.all([
        fetchHealth(),
        fetchAudit()
      ]);

      if (health) {
        const backendEl = document.getElementById('status-storage-backend');
        if (backendEl) {
          backendEl.innerHTML = `<i data-lucide="database" style="width:12px;height:12px;"></i> STOCKAGE : ${(health.storage_backend || 'SQLITE').toUpperCase()} | API : OPÉRATIONNELLE`;
          if (window.lucide) window.lucide.createIcons();
        }

        const schedEl = document.getElementById('status-scheduler-label');
        if (schedEl && health.scheduler) {
          schedEl.innerHTML = `<i data-lucide="clock" style="width:12px;height:12px;"></i> ${t('status.scheduler_label')} : ${(health.scheduler.status || 'ACTIVE').toUpperCase()}`;
          if (window.lucide) window.lucide.createIcons();
        }
      }

      if (audit && audit.reports_summary) {
        const rep = audit.reports_summary;
        const scoreEl = document.getElementById('status-val-score');
        const obsEl = document.getElementById('status-total-obs');
        const anomaliesEl = document.getElementById('status-anomalies-count');

        if (scoreEl) scoreEl.textContent = `${((rep.score_global || 1.0) * 100).toFixed(1)}%`;
        if (obsEl) obsEl.textContent = `${(rep.total_public || 0).toLocaleString()} ${t('common.records')}`;
        if (anomaliesEl) anomaliesEl.innerHTML = `<i data-lucide="alert-circle" style="width:14px;height:14px;"></i> ANOMALIES : ${rep.nb_anomalies || 0}`;

        const rawTag = document.getElementById('raw-count-tag');
        const cleanTag = document.getElementById('clean-count-tag');
        const publicTag = document.getElementById('public-count-tag');

        if (rawTag) rawTag.textContent = `${rep.total_raw || 0} ${t('common.records')}`;
        if (cleanTag) cleanTag.textContent = `${rep.total_clean || 0} ${t('common.records')}`;
        if (publicTag) publicTag.textContent = `${rep.total_public || 0} ${t('common.records')}`;
        if (window.lucide) window.lucide.createIcons();
      }

      // Render live audit logs
      const logsContainer = document.getElementById('audit-logs-list');
      if (logsContainer) {
        if (audit && audit.logs && audit.logs.length > 0) {
          logsContainer.innerHTML = audit.logs.map(log => `
            <div class="flex justify-between items-center" style="padding:6px 0;border-bottom:1px solid var(--border);">
              <span class="mono-xs text-muted">[${log.agent || 'Agent'}] ${log.type_operation || 'op'}</span>
              <span class="mono-xs text-cyan">${log.valeur_apres || ''}</span>
              <span class="mono-xs text-muted">${log.timestamp || ''}</span>
            </div>
          `).join('');
        } else {
          logsContainer.innerHTML = `<p class="mono-xs text-muted">Aucun journal d'anomalie en base de données. Tous les pipelines sont nominaux.</p>`;
        }
      }
    } catch (err) {
      console.warn('StatusView live load error:', err);
    }
  }
};
