import { initRouter, rerenderCurrent } from './router.js';
import { t, setLang, getLang } from './i18n.js';

document.addEventListener('DOMContentLoaded', () => {
  const toggle = document.getElementById('menu-toggle');
  const closeBtn = document.getElementById('menu-close');
  const mobileNav = document.getElementById('mobile-nav');
  const overlay = document.getElementById('mobile-nav-overlay');

  function openMenu() {
    mobileNav.classList.add('open');
    overlay.classList.add('open');
    toggle.setAttribute('aria-expanded', 'true');
    mobileNav.setAttribute('aria-hidden', 'false');
    document.body.style.overflow = 'hidden';
    if (window.lucide) window.lucide.createIcons();
  }

  function closeMenu() {
    mobileNav.classList.remove('open');
    overlay.classList.remove('open');
    toggle.setAttribute('aria-expanded', 'false');
    mobileNav.setAttribute('aria-hidden', 'true');
    document.body.style.overflow = '';
  }

  if (toggle) toggle.addEventListener('click', openMenu);
  if (closeBtn) closeBtn.addEventListener('click', closeMenu);
  if (overlay) overlay.addEventListener('click', closeMenu);

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeMenu();
  });

  // Navigation itself is handled by the <a href="#/..."> links + the router's
  // hashchange listener; here we only need to close the drawer.
  document.querySelectorAll('.mobile-nav-tab').forEach(tab => {
    tab.addEventListener('click', closeMenu);
  });

  const langBtn = document.getElementById('lang-toggle');
  const langLabel = document.getElementById('lang-label');

  /** Translate the static shell (header, footer, drawer). Does NOT re-render the view. */
  function applyShellLang(lang) {
    document.documentElement.lang = lang;
    if (langLabel) langLabel.textContent = lang.toUpperCase();
    document.querySelectorAll('[data-i18n]').forEach(el => {
      el.textContent = t(el.getAttribute('data-i18n'));
    });
  }

  if (langBtn) {
    langBtn.addEventListener('click', () => {
      const next = getLang() === 'fr' ? 'en' : 'fr';
      setLang(next);
      applyShellLang(next);
      rerenderCurrent();
    });
  }

  applyShellLang(getLang());
  initRouter(); // exactly one initial render
});
