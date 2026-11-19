import globals from 'globals';

const rules = {
  // главное: несуществующие имена и повторы объявлений
  'no-undef': 'error',
  // builtinGlobals: false — иначе каждое объявление в файле считается «переопределением встроенного».
  'no-redeclare': ['error', { builtinGlobals: false }],
  'no-dupe-keys': 'error',
  'no-dupe-args': 'error',
  'no-dupe-class-members': 'error',
  // заведомо мёртвый код
  'no-unreachable': 'error',
  'no-constant-condition': ['error', { checkLoops: false }],
  'no-unused-vars': ['warn', { args: 'none', caughtErrors: 'none', varsIgnorePattern: '^_' }],
  // частые источники тихих багов
  'use-isnan': 'error',
  'valid-typeof': 'error',
  'no-unsafe-negation': 'error',
  'no-self-assign': 'error',
  'no-fallthrough': 'error',
  'getter-return': 'error',
  'no-async-promise-executor': 'error',
  'require-atomic-updates': 'off',
  // разметка — только шаблонами lit-html (ADR-0013, раздел 7): строка в DOM не вставляется
  'no-restricted-syntax': ['error',
    { selector: "AssignmentExpression[left.property.name=/^(innerHTML|outerHTML)$/]",
      message: 'Разметка — шаблоном html`` и render() (ui/html.js), а не строкой в innerHTML/outerHTML.' },
    { selector: "CallExpression[callee.property.name='insertAdjacentHTML']",
      message: 'Разметка — шаблоном html`` и render() (ui/html.js), а не insertAdjacentHTML.' },
  ],
  'no-restricted-imports': ['error', { patterns: [{ group: ['**/unsafe-html.js'],
    message: 'unsafeHTML не используется: строка с разметкой в страницу не вставляется.' }] }],
};

export default [
  {
    files: ['static/js/**/*.js'],
    languageOptions: {
      ecmaVersion: 2023,
      sourceType: 'module',
      globals: { ...globals.browser, ...globals.es2021 },
    },
    rules,
  },
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
