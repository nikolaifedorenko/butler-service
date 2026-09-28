import fs from 'node:fs';
import globals from 'globals';

/* Список глобальных имён интерфейса генерируется (tools/gen_js_globals.py):
   фронтенд пока на обычных скриптах, поэтому функции одного файла видны другим
   через глобальную область. Без этого списка ESLint считал бы их неопределёнными,
   а со списком — ловит настоящие ошибки вида «вызвали функцию, которой нет»
   (именно так интерфейс показывал пустые разделы: navigate() ссылался на
   loadNight/loadCars, которых в коде не существовало). */
const gen = JSON.parse(
  fs.readFileSync(new URL('./tools/js_globals.json', import.meta.url), 'utf8'));

const rules = {
  // главное: несуществующие имена и повторы объявлений
  'no-undef': 'error',
  // builtinGlobals: false — список глобальных имён проекта передаётся в languageOptions,
  // иначе каждое объявление в файле считается «переопределением встроенного».
  // Дубли между файлами ловит tools/gen_js_globals.py (он же падает на них).
  'no-redeclare': ['error', { builtinGlobals: false }],
  'no-dupe-keys': 'error',
  'no-dupe-args': 'error',
  'no-dupe-class-members': 'error',
  // заведомо мёртвый код
  'no-unreachable': 'error',
  'no-constant-condition': ['error', { checkLoops: false }],
  'no-unused-vars': ['warn', { args: 'none', varsIgnorePattern: '^_' }],
  // частые источники тихих багов
  'use-isnan': 'error',
  'valid-typeof': 'error',
  'no-unsafe-negation': 'error',
  'no-self-assign': 'error',
  'no-fallthrough': 'error',
  'getter-return': 'error',
  'no-async-promise-executor': 'error',
  'require-atomic-updates': 'off',
};

/* Имена, объявленные в одном файле, а используемые в других: ESLint анализирует
   файл изолированно и счёл бы их мёртвыми. Подставляем их в varsIgnorePattern
   ПО ФАЙЛАМ — правило остаётся включённым и продолжает находить настоящий
   неиспользуемый код. */
const rx = s => s.replace(/[$]/g, '\\$&');
const crossFile = Object.fromEntries(
  Object.entries(gen.used_elsewhere || {}).map(([file, names]) => [
    `static/js/${file}`,
    { rules: { ...rules, 'no-unused-vars': ['warn', {
        args: 'none', caughtErrors: 'none',
        varsIgnorePattern: names.length ? `^(${names.map(rx).join('|')})$` : '^_',
      }] } },
  ]),
);

export default [
  {
    files: ['static/js/**/*.js'],
    languageOptions: {
      ecmaVersion: 2023,
      sourceType: 'script',
      globals: { ...globals.browser, ...globals.es2021, ...gen.globals },
    },
    rules,
  },
  ...Object.entries(crossFile).map(([file, cfg]) => ({ files: [file], ...cfg })),
  {
    // service worker — другая среда: self, caches, clients
    files: ['static/sw.js'],
    languageOptions: {
      ecmaVersion: 2023,
      sourceType: 'script',
      globals: { ...globals.serviceworker, ...globals.es2021 },
    },
    rules,
  },
  {
    ignores: ['tools/node_modules/**', 'node_modules/**', 'data/**', 'templates/**'],
  },
];
