/* Тема оформления: светлая, тёмная или «как в системе» (ADR-0013, раздел 7).
   Подключается в <head> обычным скриптом, чтобы тема применилась до первой отрисовки (иначе
   страница мигает). Значение — в localStorage; атрибут data-theme на <html> читают tokens.css:
   «как в системе» — атрибута нет, действует prefers-color-scheme. */
(function () {
  var KEY = 'butler-theme';
  var MODES = ['auto', 'light', 'dark'];
  var root = document.documentElement;

  function read() {
    try { var v = localStorage.getItem(KEY); return MODES.indexOf(v) >= 0 ? v : 'auto'; } catch (e) { return 'auto'; }
  }
  function apply(mode) {
    if (mode === 'auto') root.removeAttribute('data-theme'); else root.setAttribute('data-theme', mode);
    root.setAttribute('data-theme-mode', mode);
  }
  function set(mode) {
    if (MODES.indexOf(mode) < 0) mode = 'auto';
    try { if (mode === 'auto') localStorage.removeItem(KEY); else localStorage.setItem(KEY, mode); } catch (e) { /* без хранилища тема живёт до перезагрузки */ }
    apply(mode);
  }
  function next() { set(MODES[(MODES.indexOf(read()) + 1) % MODES.length]); }

  apply(read());
  window.butlerTheme = { get: read, set: set, next: next };
  document.addEventListener('click', function (e) {
    if (e.target.closest && e.target.closest('#theme-toggle')) next();
  });
})();
