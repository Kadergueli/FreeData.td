import { initRouter, navigateTo, getCurrentRoute, getCurrentParams } from './router.js';
import { t, setLang, getLang } from './i18n.js';

document.addEventListener('DOMContentLoaded', () => {
  initRouter();

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

  document.querySelectorAll('.mobile-nav-tab').forEach(tab => {
    tab.addEventListener('click', (e) => {
      const route = e.currentTarget.getAttribute('data-route');
      if (route) {
        document.querySelectorAll('.mobile-nav-tab').forEach(t => t.classList.remove('active'));
        e.currentTarget.classList.add('active');
        window.dispatchEvent(new CustomEvent('navigate', { detail: { route } }));
        closeMenu();
      }
    });
  });

  const langBtn = document.getElementById('lang-toggle');
  const langLabel = document.getElementById('lang-label');

  function applyLang(lang) {
    document.documentElement.lang = lang;
    if (langLabel) langLabel.textContent = lang.toUpperCase();
    document.querySelectorAll('[data-i18n]').forEach(el => {
      const key = el.getAttribute('data-i18n');
      el.textContent = t(key);
    });
    const currentRoute = getCurrentRoute();
    const currentParams = getCurrentParams();
    if (currentRoute) navigateTo(currentRoute, currentParams);
  }

  if (langBtn) {
    langBtn.addEventListener('click', () => {
      const next = getLang() === 'fr' ? 'en' : 'fr';
      setLang(next);
      applyLang(next);
    });
  }

  const footerTermsBtn = document.getElementById('footer-terms-btn');
  if (footerTermsBtn) {
    footerTermsBtn.addEventListener('click', () => {
      navigateTo('terms');
    });
  }

  applyLang(getLang());
});
