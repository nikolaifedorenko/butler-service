/* Поля форм шаблонами lit-html (ADR-0013, раздел 7): подпись над полем, текстовое поле, флажок, список.
   Те же элементы и идентификаторы, что у строковых помощников sfRow / sfInput / sfCheck / sfSelect раздела
   «Шахматка», которые остаются для файлов, ещё не переехавших на шаблоны. */
import { html } from './html.js';

/* подпись над элементом управления */
export const fieldRow = (label, control) => html`<label class="field"><span>${label}</span>${control}</label>`;
/* текстовое поле; type — text, date, time… (type раньше value: у date значение задаётся после типа) */
export const textInput = (id, value = '', type = 'text') => html`<input id=${id} type=${type} .value=${String(value ?? '')}>`;
export const checkField = (id, label, on) => html`<label class="chk"><input id=${id} type="checkbox" .checked=${!!on}> ${label}</label>`;
/* список из пар [значение, подпись]; выбран тот, чьё значение равно value */
export const selectField = (id, options, value) => html`<select id=${id}>${options.map(([v, t]) =>
  html`<option value=${String(v)} ?selected=${String(v) === String(value)}>${t}</option>`)}</select>`;
/* вариант списка: пустое значение и null считаются равными (как в прежних формах) */
export const optionView = (v, t, cur) => html`<option value=${String(v ?? '')} ?selected=${String(v ?? '') === String(cur ?? '')}>${t}</option>`;

/* ── мост к общей области имён (генерируется tools/gen_js_globals.py; уйдёт вместе с переходом файла на import/export) ── */
Object.assign(globalThis, {
  fieldRow,
  textInput,
  checkField,
  selectField,
  optionView,
});
/* ── конец моста ── */
