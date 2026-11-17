/* Копирует сторонние файлы интерфейса из node_modules в static/vendor/ (без сборки).
   Запуск: npm run vendor. Копируем только то, что нужно интерфейсу. */
import fs from 'node:fs';
import path from 'node:path';

const ROOT = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');
const FILES = {
  'lit-html': ['lit-html.js', 'LICENSE'],
};

for (const [pkg, files] of Object.entries(FILES)) {
  const out = path.join(ROOT, 'static/vendor', pkg);
  fs.mkdirSync(out, { recursive: true });
  for (const f of files) fs.copyFileSync(path.join(ROOT, 'node_modules', pkg, f), path.join(out, f));
  const version = JSON.parse(fs.readFileSync(path.join(ROOT, 'node_modules', pkg, 'package.json'), 'utf8')).version;
  console.log(`✓ ${pkg} ${version} → static/vendor/${pkg}/`);
}
