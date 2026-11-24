'use strict';

/* ══════════════════════════════════════════════════════════════════
   СТРАНИЦА ПЕЧАТИ: сигналы готовности и завершения родителю.
   Внешний файл, а не inline-скрипт: страница показывается во фрейме
   srcdoc и наследует CSP приложения — script-src 'self' разрешает
   этот файл, inline-скрипты блокирует (A1, аудит 25.10.2026).
   Родитель по сообщению butler_print_done удаляет фрейм.
   ══════════════════════════════════════════════════════════════════ */
window.addEventListener('afterprint', () => {
  parent.postMessage({ butler_print_done: true }, '/');
}, { once: true });
window.addEventListener('load', () => { parent.postMessage({ butler_print_ready: true }, '/'); }, { once: true });
