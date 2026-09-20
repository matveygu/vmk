/* Shared, progressive enhancement for the portal shell. */
(function () {
  'use strict';
  var body = document.body;
  var menu = document.getElementById('dsSidenav');
  var menuToggle = document.getElementById('dsMenuToggle');
  var userPill = document.getElementById('dsUserPill');
  var narrow = window.matchMedia('(max-width: 1100px)');
  var previousFocus = null;
  var modalFocus = new WeakMap();
  var focusable = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex="0"]';
  function drawerMode() { return body.classList.contains('ds-public') || narrow.matches; }

  window.dsToggleTheme = function () {
    var root = document.documentElement;
    var theme = root.dataset.theme === 'dark' ? 'light' : 'dark';
    root.dataset.theme = theme;
    try { localStorage.setItem('msu_theme', theme); } catch (e) {}
  };
  function syncMenu() {
    if (!menu) return;
    var open = body.classList.contains('ds-sidenav-open');
    menu.inert = drawerMode() && !open;
    if (menuToggle) menuToggle.setAttribute('aria-expanded', String(open));
    if (drawerMode() && open) {
      menu.setAttribute('role', 'dialog');
      menu.setAttribute('aria-modal', 'true');
    } else {
      menu.removeAttribute('role');
      menu.removeAttribute('aria-modal');
    }
  }
  window.dsToggleSidenav = function () {
    if (!menu) return;
    if (body.classList.contains('ds-sidenav-open')) { window.dsCloseSidenav(); return; }
    previousFocus = document.activeElement;
    body.classList.add('ds-sidenav-open');
    syncMenu();
    var first = menu.querySelector('.ds-sidenav-close');
    if (first) first.focus();
  };
  window.dsCloseSidenav = function () {
    var wasOpen = body.classList.contains('ds-sidenav-open');
    body.classList.remove('ds-sidenav-open');
    syncMenu();
    if (wasOpen && previousFocus) previousFocus.focus();
  };
  function closeUserMenu() {
    if (!userPill) return;
    userPill.classList.remove('open');
    userPill.querySelector('button').setAttribute('aria-expanded', 'false');
  }
  window.dsToggleUserMenu = function () {
    if (!userPill) return;
    var open = userPill.classList.toggle('open');
    userPill.querySelector('button').setAttribute('aria-expanded', String(open));
  };
  window.dsOpenModal = function (id) {
    var el = document.getElementById(id);
    if (!el) return;
    modalFocus.set(el, document.activeElement);
    var dialog = el.querySelector('.ds-modal') || el;
    dialog.setAttribute('role', 'dialog');
    dialog.setAttribute('aria-modal', 'true');
    var heading = dialog.querySelector('h3, h2');
    if (heading) {
      if (!heading.id) heading.id = id + '-title';
      dialog.setAttribute('aria-labelledby', heading.id);
    }
    el.classList.add('open');
    body.classList.add('ds-modal-active');
    var first = el.querySelector('input:not([type="hidden"]), select, textarea, button');
    if (first) first.focus();
  };
  window.dsCloseModal = function (id) {
    var el = document.getElementById(id);
    if (!el) return;
    el.classList.remove('open');
    if (!document.querySelector('.ds-modal-scrim.open')) body.classList.remove('ds-modal-active');
    var prev = modalFocus.get(el);
    if (prev) prev.focus();
  };
  window.dsToggleNews = function (id, btn) {
    var el = document.getElementById('ds-news-body-' + id);
    if (!el) return;
    var open = el.style.display !== 'none';
    el.style.display = open ? 'none' : 'block';
    btn.classList.toggle('open', !open);
    btn.setAttribute('aria-expanded', String(!open));
    var label = btn.querySelector('span');
    if (label) label.textContent = open ? 'Показать' : 'Скрыть';
  };
  document.addEventListener('click', function (e) {
    if (userPill && !userPill.contains(e.target)) closeUserMenu();
    if (e.target.classList.contains('ds-modal-scrim')) window.dsCloseModal(e.target.id);
  });
  document.addEventListener('keydown', function (e) {
    var modal = document.querySelector('.ds-modal-scrim.open');
    if (e.key === 'Escape') {
      if (modal) { window.dsCloseModal(modal.id); return; }
      if (userPill && userPill.classList.contains('open')) { closeUserMenu(); userPill.querySelector('button').focus(); }
      window.dsCloseSidenav();
    }
    var trap = modal || (drawerMode() && body.classList.contains('ds-sidenav-open') ? menu : null);
    if (e.key === 'Tab' && trap) {
      var elements = Array.from(trap.querySelectorAll(focusable)).filter(function (el) { return el.getClientRects().length && el.type !== 'hidden'; });
      var first = elements[0], last = elements[elements.length - 1];
      if (!first) return;
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    }
  });
  document.querySelectorAll('.ds-sidenav-item.active').forEach(function (el) { el.setAttribute('aria-current', 'page'); });
  if (narrow.addEventListener) narrow.addEventListener('change', function () { window.dsCloseSidenav(); });
  syncMenu();
})();
