import { HomeView } from './views/home.js';
import { SectorsView } from './views/sectors.js';
import { DataView } from './views/data.js';
import { SourcesView } from './views/sources.js';
import { InsightsView } from './views/insights.js';
import { ApiView } from './views/api.js';
import { StatusView } from './views/status.js';
import { TermsView } from './views/terms.js';
import { t } from './i18n.js';

const routes = [
  { id: 'home', navKey: 'nav.mission', view: HomeView },
  { id: 'sectors', navKey: 'nav.explorer', view: SectorsView },
  { id: 'data', navKey: 'nav.repository', view: DataView },
  { id: 'sources', navKey: 'nav.sources', view: SourcesView },
  { id: 'insights', navKey: 'nav.insights', view: InsightsView },
  { id: 'api', navKey: 'nav.api', view: ApiView },
  { id: 'status', navKey: 'nav.status', view: StatusView },
  { id: 'terms', navKey: 'nav.terms', view: TermsView },
];

let _currentRouteId = 'home';
let _currentParams = {};

export function getCurrentRoute() { return _currentRouteId; }
export function getCurrentParams() { return _currentParams; }

export function refreshNavLabels() {
  document.querySelectorAll('.nav-tab[data-route]').forEach(tab => {
    const route = routes.find(r => r.id === tab.dataset.route);
    if (route) tab.textContent = t(route.navKey);
  });
  document.querySelectorAll('.mobile-nav-tab [data-i18n]').forEach(el => {
    el.textContent = t(el.getAttribute('data-i18n'));
  });
}

export function navigateTo(routeId, params = {}) {
  const route = routes.find(r => r.id === routeId);
  if (!route) return;

  _currentRouteId = routeId;
  _currentParams = params;

  document.querySelectorAll('.nav-tab').forEach(tab => {
    const r = routes.find(r => r.id === tab.dataset.route);
    if (r) tab.textContent = t(r.navKey);
    tab.classList.toggle('active', tab.dataset.route === routeId);
  });

  document.querySelectorAll('.mobile-nav-tab').forEach(tab => {
    tab.classList.toggle('active', tab.dataset.route === routeId);
  });

  const main = document.getElementById('app-main');
  main.innerHTML = `<div class="view active">${route.view.render(params)}</div>`;

  if (window.lucide) window.lucide.createIcons();

  if (typeof route.view.init === 'function') {
    route.view.init(params);
  }

  window.scrollTo({ top: 0, behavior: 'smooth' });
}

export function initRouter() {
  const navContainer = document.querySelector('.nav-tabs');
  if (navContainer) {
    navContainer.addEventListener('click', (e) => {
      const tab = e.target.closest('.nav-tab');
      if (!tab) return;
      navigateTo(tab.dataset.route);
    });
  }

  window.addEventListener('navigate', (e) => {
    if (e.detail && e.detail.route) navigateTo(e.detail.route);
  });

  navigateTo('home');

  if (window.lucide) window.lucide.createIcons();
}
