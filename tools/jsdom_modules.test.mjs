import assert from 'node:assert/strict';
import test from 'node:test';
import { importsOf, toClassic } from './jsdom_modules.mjs';

const run = code => { const win = {}; new Function('window', `return (function(){ ${toClassic(code)} }).call(window)`)(win); return win; };

test('файл без import/export не меняется', () => {
  const code = "'use strict';\nconst a = 1;\n";
  assert.equal(toClassic(code), code);
});

test('export объявлений публикуется в window, внутреннее остаётся закрытым', () => {
  const win = run("export function f() { return secret; }\nconst secret = 7;\nexport const g = 2;\nexport class C {}\n");
  assert.equal(win.f(), 7);
  assert.equal(win.g, 2);
  assert.equal(typeof win.C, 'function');
  assert.equal(win.secret, undefined);
});

test('export { a as b } и повторный экспорт из другого файла', () => {
  const win = run("const a = 5;\nexport { a as b };\n");
  assert.equal(win.b, 5);
  assert.deepEqual(new Set(importsOf("export { html } from '/static/x.js';\nimport { a, b } from './y.js';\nimport '/static/z.js';\n")),
                   new Set(['/static/x.js', './y.js', '/static/z.js']));
});

test('многострочный import убирается целиком', () => {
  const out = toClassic("import {\n  a,\n  b,\n} from './m.js';\nexport const x = a + b;\n");
  assert.ok(!/import/.test(out));
  assert.match(out, /Object\.assign\(window, \{ x \}\)/);
});

test('минифицированный файл с export{…} в середине строки тоже превращается в скрипт', () => {
  const win = run("const q=1,w=2;function f(){return q+w}export{f as html,w as other};\n//# sourceMappingURL=x.js.map\n");
  assert.equal(win.html(), 3);
  assert.equal(win.other, 2);
});

test('минифицированные import подряд на одной строке', () => {
  const code = 'import{nothing as t}from"../lit-html.js";import{directive as r}from"../directive.js";\nclass e{}export{e as unsafeHTML};\n';
  assert.deepEqual(importsOf(code), ['../lit-html.js', '../directive.js']);
  assert.ok(!/import/.test(toClassic(code)));
});

test('import с псевдонимом: локальное имя указывает на экспорт зависимости', () => {
  const win = { Directive: class Base {} };
  new Function('window', `return (function(){ ${toClassic('import{Directive as s}from"./d.js";class E extends s{}export{E as made};')} }).call(window)`)(win);
  assert.ok(new win.made() instanceof win.Directive);
});
