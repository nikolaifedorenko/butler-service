/* Загрузка интерфейса в jsdom с поддержкой ES-модулей (ADR-0013, раздел 7).

   jsdom не выполняет <script type="module">, а смоук и сценарии в jsdom (tools/*.mjs) — наша сетка
   безопасности, пока разделы переезжают на import/export. Этот загрузчик превращает модули в
   обычные скрипты: порядок загрузки — как у модулей (сначала зависимости), import убирается,
   export публикует имена в window. Файл без import/export выполняется как раньше, без обёртки.

   Ограничения (их держит код интерфейса): нет import.meta и верхнеуровневого await; два модуля не
   экспортируют одно имя. Проверки в jsdom уходят, когда все разделы переедут на Playwright (шаг 6з). */
import fs from 'node:fs';
import path from 'node:path';

const IMPORT_RE = /^import\s+(?:[\s\S]*?\s+from\s+)?(['"])([^'"]+)\1\s*;?[ \t]*$/gm;
const REEXPORT_RE = /^export\s*\{[^}]*\}\s*from\s*(['"])([^'"]+)\1\s*;?[ \t]*$/gm;
const EXPORT_LIST_RE = /\bexport\s*\{([^}]*)\}\s*;?/g;
const EXPORT_DECL_RE = /^export\s+(?:async\s+)?(?:function\*?|class|const|let|var)\s+([A-Za-z_$][\w$]*)/gm;

/** Адреса зависимостей файла: относительные и вида /static/…; внешние пакеты не поддерживаются. */
export function importsOf(code) {
  const out = [];
  for (const re of [IMPORT_RE, REEXPORT_RE]) {
    re.lastIndex = 0;
    for (const m of code.matchAll(re)) out.push(m[2]);
  }
  return out;
}

/** Модуль → обычный скрипт: без import, экспорт — присваиванием в window; файл без import/export — как есть. */
export function toClassic(code) {
  const hasModuleSyntax = /(^|[;}])\s*(import|export)\b/m.test(code);
  if (!hasModuleSyntax) return code;
  const names = [];
  let body = code.replace(REEXPORT_RE, '');
  body = body.replace(IMPORT_RE, '');
  body = body.replace(EXPORT_LIST_RE, (_, list) => {
    for (const part of list.split(',').map(s => s.trim()).filter(Boolean)) {
      const [local, exported] = part.split(/\s+as\s+/);
      names.push([exported || local, local]);
    }
    return '';
  });
  body = body.replace(EXPORT_DECL_RE, (m, name) => { names.push([name, name]); return m.replace(/^export\s+/, ''); });
  const publish = names.length
    ? `\nObject.assign(window, { ${names.map(([e, l]) => (e === l ? e : `${e}: ${l}`)).join(', ')} });` : '';
  return `(function () {\n${body}${publish}\n}).call(window);\n`;
}

function resolveImport(from, spec, root) {
  if (spec.startsWith('/')) return path.join(root, spec.replace(/^\//, '').split('?')[0]);
  if (spec.startsWith('.')) return path.resolve(path.dirname(from), spec.split('?')[0]);
  throw new Error(`jsdom_modules: пакет «${spec}» не поддерживается (${from})`);
}

/** Файлы в порядке выполнения: зависимости раньше зависящих, каждый один раз. */
export function loadOrder(entries, root) {
  const seen = new Set();
  const order = [];
  const visit = file => {
    if (seen.has(file)) return;
    seen.add(file);
    const code = fs.readFileSync(file, 'utf8');
    for (const spec of importsOf(code)) visit(resolveImport(file, spec, root));
    order.push({ file, code });
  };
  entries.forEach(visit);
  return order;
}

/** Адреса скриптов оболочки из index.html (без ?v=), в порядке документа. */
export function entriesOf(html, root) {
  return [...html.matchAll(/<script (?:type="module" )?src="([^"]+)"><\/script>/g)]
    .map(m => path.join(root, m[1].split('?v=')[0].replace(/^\//, '')));
}

/** Выполнить оболочку приложения в окне jsdom. Возвращает список загруженных файлов (относительно корня). */
export function loadApp(window, html, root, { log } = {}) {
  const loaded = [];
  for (const { file, code } of loadOrder(entriesOf(html, root), root)) {
    const rel = path.relative(root, file);
    if (!fs.existsSync(file)) { log?.('❌ скрипт не найден: ' + rel); continue; }
    const sc = window.document.createElement('script');
    sc.textContent = toClassic(code);
    window.document.body.appendChild(sc);
    loaded.push(rel);
    log?.('загружен скрипт: ' + rel);
  }
  return loaded;
}
