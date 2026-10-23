import { HomeView } from './views/home.js';
import { SectorsView } from './views/sectors.js';
import { DataView } from './views/data.js';
import { SourcesView } from './views/sources.js';
import { InsightsView } from './views/insights.js';
import { ApiView } from './views/api.js';
import { StatusView } from './views/status.js';
import { TermsView } from './views/terms.js';
import { AdminView } from './views/admin.js';
import { destroyAllCharts } from './charts.js';
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
  { id: 'admin', navKey: 'nav.admin', view: AdminView }, // no nav tab: reached from the footer
];

let _currentRouteId = 'home';
let _currentParams = {};

export function getCurrentRoute() { return _currentRouteId; }
export function getCurrentParams() { return _currentParams; }

/* ── Hash helpers: "#/data?sector=health" ⇄ { id: 'data', params: { sector: 'health' } } ── */

export function buildHash(routeId, params = {}) {
  const qs = new URLSearchParams();
  Object.entries(params || {}).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') qs.set(k, String(v));
  });
  const q = qs.toString();
  return `#/${routeId}${q ? `?${q}` : ''}`;
}

export function parseHash(hash) {
  const raw = String(hash || '').replace(/^#\/?/, '');
  const [path, query = ''] = raw.split('?');
  const id = routes.some(r => r.id === path) ? path : 'home';
  const params = {};
  new URLSearchParams(query).forEach((v, k) => { params[k] = v; });
  return { id, params };
}

export function refreshNavLabels() {
  document.querySelectorAll('.nav-tab[data-route]').forEach(tab => {
    const route = routes.find(r => r.id === tab.dataset.route);
    if (route) tab.textContent = t(route.navKey);
  });
  document.querySelectorAll('.mobile-nav-tab [data-i18n]').forEach(el => {
    el.textContent = t(el.getAttribute('data-i18n'));
  });
}

function markActive(routeId) {
  document.querySelectorAll('.nav-tab').forEach(tab => {
    const active = tab.dataset.route === routeId;
    tab.classList.toggle('active', active);
    if (active) tab.setAttribute('aria-current', 'page');
    else tab.removeAttribute('aria-current');
  });
  document.querySelectorAll('.mobile-nav-tab').forEach(tab => {
    const active = tab.dataset.route === routeId;
    tab.classList.toggle('active', active);
    if (active) tab.setAttribute('aria-current', 'page');
    else tab.removeAttribute('aria-current');
  });
}

/** Render a route WITHOUT touching the URL. */
function renderRoute(routeId, params = {}) {
  const route = routes.find(r => r.id === routeId);
  if (!route) return;

  _currentRouteId = routeId;
  _currentParams = params;

  destroyAllCharts();
  refreshNavLabels();
  markActive(routeId);

  const main = document.getElementById('app-main');
  main.innerHTML = `<div class="view active">${route.view.render(params)}</div>`;

  if (window.lucide) window.lucide.createIcons();

  if (typeof route.view.init === 'function') {
    // A failing view must never leave the whole SPA blank.
    Promise.resolve()
      .then(() => route.view.init(params))
      .catch(err => console.error(`View "${routeId}" init failed:`, err));
  }

  window.scrollTo({ top: 0, behavior: 'auto' });
}

/** Public navigation: updates the URL hash (so Back / refresh / deep links work);
 *  the hashchange listener then renders. Same hash → re-render in place. */
export function navigateTo(routeId, params = {}) {
  if (!routes.some(r => r.id === routeId)) return;
  const target = buildHash(routeId, params);
  if (window.location.hash === target) {
    renderRoute(routeId, params);
  } else {
    window.location.hash = target;
  }
}

/** Re-render the current route (used after a language switch). */
export function rerenderCurrent() {
  renderRoute(_currentRouteId, _currentParams);
}

function renderFromHash() {
  const { id, params } = parseHash(window.location.hash);
  renderRoute(id, params);
}

export function initRouter() {
  window.addEventListener('hashchange', renderFromHash);
  // Legacy hook: other modules may dispatch a 'navigate' CustomEvent.
  window.addEventListener('navigate', (e) => {
    if (e.detail && e.detail.route) navigateTo(e.detail.route, e.detail.params || {});
  });
  renderFromHash(); // single initial render (was rendered twice before)
}
