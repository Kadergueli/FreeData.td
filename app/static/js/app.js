import { initRouter, rerenderCurrent } from './router.js';
import { t, setLang, getLang } from './i18n.js';
import { showToast } from './ui.js';

let _deferredInstallPrompt = null;

window.addEventListener('beforeinstallprompt', (e) => {
  e.preventDefault();
  _deferredInstallPrompt = e;
  const installBtn = document.getElementById('pwa-install-btn');
  if (installBtn) {
    installBtn.hidden = false;
    if (window.lucide) window.lucide.createIcons();
  }
});

window.addEventListener('appinstalled', () => {
  _deferredInstallPrompt = null;
  const installBtn = document.getElementById('pwa-install-btn');
  if (installBtn) installBtn.hidden = true;
});

if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js', { scope: '/' }).catch(() => {});
  });
}

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

  const installBtn = document.getElementById('pwa-install-btn');
  const isStandalone = window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone === true;
  const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent) && !window.MSStream;
  if (installBtn && !isStandalone && (_deferredInstallPrompt || isIOS)) {
    installBtn.hidden = false;
  }
  if (installBtn) {
    installBtn.addEventListener('click', async () => {
      if (_deferredInstallPrompt) {
        _deferredInstallPrompt.prompt();
        const choice = await _deferredInstallPrompt.userChoice.catch(() => null);
        if (choice && choice.outcome === 'accepted') {
          _deferredInstallPrompt = null;
          installBtn.hidden = true;
        }
      } else if (isIOS) {
        showToast(t('nav.install_ios'), 'info');
      }
    });
  }

  applyShellLang(getLang());
  initRouter(); // exactly one initial render
});
