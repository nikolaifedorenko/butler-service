/* Смоук прототипа «График = 4 слоя» (docs/grafik-4-sloya-prototype.html): jsdom, БЕЗ сервера.

Зачем: прототип — автономный HTML со встроенным мини-движком (окна из Табеля, переработки ДЯ/ДН,
недоработка, банк при закрытии, каскад, флаги из Графика). Смоук фиксирует, что демо-примеры владельца
от 12.10.2026 воспроизводятся числами (Петров 05.10: план 12ч/факт 11ч30м/недоработка 30м/ДЯ 30м;
Иванова 05.10: план 9ч/факт 8ч/недоработка 1ч→банк/ДЯ 5ч+ДН 1ч) и что все 4 слоя переключаются и рисуются.
Прототип v2.1: учтены решения владельца от 12.10.2026 — Q1 (окно ВСЕГДА из кода Табеля, переключателя
режима нет, ночная смена Графика часы не меняет — демо Петров 06.10), замечание 1 / Q4 / Q6
(«недопуск» не добавляется), замечание 2 (границы ДЯ/ДН — из настроек).

Запуск: npm run smoke:proto   (нужен jsdom: npm install)
Код возврата: 0 — пройден, 2 — есть проваленные проверки. */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { JSDOM, VirtualConsole } from 'jsdom';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '..');
const file = path.resolve(process.argv[2] || path.join(ROOT, 'docs/grafik-4-sloya-prototype.html'));
const html = fs.readFileSync(file, 'utf8');
const errors = [];
const vc = new VirtualConsole();
vc.on('jsdomError', e => errors.push('jsdomError: ' + (e.stack || e.message)));
vc.on('error', (...a) => errors.push('console.error: ' + a.join(' ')));
const dom = new JSDOM(html, { runScripts: 'dangerously', pretendToBeVisual: true, virtualConsole: vc });
const { window } = dom;
const doc = window.document;
const $ = s => doc.querySelector(s);
const $$ = s => Array.from(doc.querySelectorAll(s));
const click = el => { if (!el) throw new Error('нет элемента для клика: ' + el); el.dispatchEvent(new window.MouseEvent('click', { bubbles: true })); };
let fails = 0, total = 0;
const check = (name, cond, extra = '') => {
  total++;
  if (!cond) fails++;
  console.log((cond ? 'PASS  ' : 'FAIL  ') + name + (extra ? '  — ' + extra : ''));
};
const rowOf = (sel, name) => $$(sel).filter(tr => tr.textContent.includes(name))[0];
const cellOf = (emp, day) => {
  const tr = rowOf('#layer-l0 table.grid tr', emp);
  return tr ? tr.querySelectorAll('.tcell')[day - 1] : null;
};
const l1cellOf = (emp, day) => {
  const tr = rowOf('#layer-l1 table.grid tr', emp);
  return tr ? tr.querySelectorAll('.scell')[day - 1] : null;
};
const l3cellOf = (emp, day) => {
  const tr = rowOf('#layer-l3 table.grid tr', emp);
  return tr ? tr.querySelectorAll('.cellbtn')[day - 1] : null;
};
const gotoLayer = id => click($('.subtab[data-layer="' + id + '"]'));
const bodyText = () => doc.body.textContent;

/* ── 0. Каркас ── */
check('нет ошибок JS при загрузке', errors.length === 0, errors.join(' | '));
check('бренд прототипа v2.1', /Батлер · прототип v2\.1/.test(bodyText()));
check('нет переключателя режима окна — Q1 решён (окно всегда из кода Табеля)', $$('#mode-seg').length === 0 && /Решения владельца от 12\.10\.2026 учтены/.test(bodyText()));
check('меню: 4 пункта', $$('#sidenav .navbtn').length === 4);
check('меню: «График» активен', $('.navbtn[data-nav="grafik"]').classList.contains('active'));

/* ── 1. Меню-заглушки ── */
click($('.navbtn[data-nav="board"]'));
check('Доска: заглушка с Q7', $('#view-board').classList.contains('on') && /Q7/.test($('#view-board').textContent));
click($('.navbtn[data-nav="settings"]'));
check('Настройки: ссылка на ред. 7', /ред\. 7/.test($('#view-settings').textContent));
click($('.navbtn[data-nav="grafik"]'));
check('возврат в График', $('#view-grafik').classList.contains('on'));

/* ── 2. Под-вкладки слоёв ── */
check('5 под-вкладок', $$('#subtabs .subtab').length === 5);
['l0', 'l1', 'l2', 'l3', 'scheme'].forEach(id => {
  gotoLayer(id);
  check('под-вкладка ' + id + ' открывается', $('#layer-' + id).classList.contains('on'));
});
gotoLayer('l0');

/* ── 3. Слой 0 · Табель ── */
check('L0: сетка 3 × 14', $$('#layer-l0 .tcell').length === 42, 'ячеек: ' + $$('#layer-l0 .tcell').length);
check('L0: код «Я 8» виден', /Я 8/.test($('#l0-grid').textContent));
check('L0: код «Я 10,75» виден', /Я 10,75/.test($('#l0-grid').textContent));
check('L0: отпуск Ивановой 7–9 (✎ вручную)', cellOf('Иванова', 7).textContent.includes('ОТ') && cellOf('Иванова', 7).textContent.includes('✎'));
check('L0: НН Сидоровой 8 (✎ вручную)', cellOf('Сидорова', 8).textContent.includes('НН'));
check('L0: выходной в субботу (3.10)', cellOf('Петров', 3).textContent.includes('В'));
check('L0: «Сбросить (3)» у Ивановой', rowOf('#layer-l0 tr', 'Иванова').textContent.includes('Сбросить (3)'));
check('L0: «Сбросить» запрещён у Петрова (автозаполнение)', rowOf('#layer-l0 tr', 'Петров').querySelector('.reset-btn').disabled);
check('L0: нота про заявления из Табеля', /заявления \(отпуск, за свой счёт/.test($('#layer-l0').textContent));

/* модалка кода */
click(cellOf('Иванова', 1));
let m = $('#modal-host .modal');
check('L0: модалка кода открылась', !!m && /Табель · Иванова Анна/.test(m.textContent));
check('L0: активен текущий код «Я 8»', m.querySelector('#code-pick button.active').dataset.code === 'Я 8');
click(Array.from(m.querySelectorAll('#code-pick button')).find(b => b.dataset.code === 'Б'));
check('L0: код «Б» сохранён, помечен ✎', cellOf('Иванова', 1).textContent.includes('Б') && cellOf('Иванова', 1).textContent.includes('✎'));
check('L0: тост про перегенерацию Графика', /График дня перегенерирован/.test(bodyText()));
click(cellOf('Иванова', 1));
click(Array.from($('#modal-host').querySelectorAll('#code-pick button')).find(b => b.dataset.code === 'Я 8'));
check('L0: возврат к «Я 8» снимает ✎ (авто)', cellOf('Иванова', 1).textContent.includes('авто') && !cellOf('Иванова', 1).textContent.includes('✎'));

/* сброс */
click(rowOf('#layer-l0 tr', 'Сидорова').querySelector('.reset-btn'));
m = $('#modal-host .modal');
check('L0: модалка сброса перечисляет «8.10 — НН»', /8\.10 — «НН»/.test(m.textContent));
click(m.querySelector('#reset-ok'));
check('L0: после сброса 8.10 = «Я 10,75» авто', cellOf('Сидорова', 8).textContent.includes('Я 10,75') && cellOf('Сидорова', 8).textContent.includes('авто'));
check('L0: кнопка «Сбросить» стала запрещена', rowOf('#layer-l0 tr', 'Сидорова').querySelector('.reset-btn').disabled);
check('L0: тост сброса', /сброшен к автозаполнению/.test(bodyText()));

/* ── 4. Слой 1 · План / График ── */
gotoLayer('l1');
check('L1: сетка 3 × 14', $$('#layer-l1 .scell').length === 42);
const iv5 = l1cellOf('Иванова', 5);
check('L1: ручная смена Ивановой 08:00–17:00 + «СМ»', /08:00–17:00/.test(iv5.textContent) && /СМ/.test(iv5.innerHTML));
check('L1: отпрос 12:00–13:00 (✂)', /✂ 12:00–13:00/.test(iv5.textContent));
const pe5 = l1cellOf('Петров', 5);
check('L1: табельная смена Петрова 08:00–20:00 «табельное окно»', /08:00–20:00/.test(pe5.textContent) && /табельное окно/.test(pe5.textContent));
const pe6 = l1cellOf('Петров', 6);
check('L1: Петров 06.10 — ночная смена «СМ» 20:00–08:00 (демо Q1)', /20:00–08:00/.test(pe6.textContent) && /СМ/.test(pe6.innerHTML) && /ручная из справочника/.test(pe6.textContent));
check('L1: в легенде нет «⛔ недопуск» (замечание 1)', !/⛔/.test($('#layer-l1').textContent));
check('L1: у выходного «—» / «выходной»', /выходной/.test(l1cellOf('Петров', 4).textContent));
check('L1: модалка дня содержит «Табель (слой 0): «Я 8» — не меняется отсюда»', (() => {
  click(iv5);
  const mm = $('#modal-host .modal');
  return /не меняется отсюда/.test(mm.textContent) && /«Я 8»/.test(mm.textContent);
})());
check('L1: в модалке есть «Отпросился на всю смену» и НЕТ «Недопуск к работе» (Q4/Q6)', !!$('#m-timeoff-full') && !$('#m-notadm'));
check('L1: в модалке один тип отсутствия — «за счёт часов» (Q4)', $$('#m-abs-kind option').length === 1);
check('L1: нота окна — стандартное окно «Я 8», ручная смена окно не меняет (Q1)', /стандартное окно 09:00–18:00/.test($('#m-winnote').textContent) && /окно не меняет/.test($('#m-winnote').textContent));
check('L1: нота «меняет только флаги… На часы Табеля График не влияет»', /меняет только флаги/.test($('#modal-host').textContent) && /На часы Табеля График не влияет/.test($('#modal-host').textContent));
click($('#modal-host [data-x]'));
check('L1: модалка закрылась по «Отмена»', !$('#modal-host .modal'));

/* модалка на чистом дне: отпрос на всю смену */
click(l1cellOf('Сидорова', 12));
check('L1: «Отпросился на всю смену» добавляет интервал 08:00–20:00', (() => {
  click($('#m-timeoff-full'));
  return /08:00–20:00/.test($('#m-abs-list').textContent) && /Отпросился на всю смену 08:00–20:00/.test(bodyText());
})());
click($('#modal-host [data-x]'));

/* Заполнить из Табеля */
click($('#l1-refill'));
check('L1: после «Заполнить из Табеля» ручная смена Ивановой убрана (авто 09:00–18:00)', /09:00–18:00/.test(l1cellOf('Иванова', 5).textContent) && !/СМ/.test(l1cellOf('Иванова', 5).innerHTML));
check('L1: отсутствие ✂ сохранено', /✂ 12:00–13:00/.test(l1cellOf('Иванова', 5).textContent));
check('L1: тост перегенерации', /перегенерирован из Табеля/.test(bodyText()));
/* восстановим ручную смену 08:00–17:00 через модалку (пример владельца №2) */
click(l1cellOf('Иванова', 5));
$('#m-from').value = '08:00'; $('#m-to').value = '17:00';
click($('#m-save'));
check('L1: ручная смена 08:00–17:00 восстановлена (СМ)', /08:00–17:00/.test(l1cellOf('Иванова', 5).textContent) && /СМ/.test(l1cellOf('Иванова', 5).innerHTML));
check('L1: тост «часы Табеля не менялись»', /часы Табеля не менялись/.test(bodyText()));
/* «Заполнить из Табеля» убирало и ночную смену Петрова 06.10 — вернём её через справочник (демо Q1) */
click(l1cellOf('Петров', 6));
$('#m-shift').value = 'NIGHT12';
click($('#m-save'));
check('L1: ночная смена Петрова 06.10 возвращена из справочника (СМ 20:00–08:00)', /20:00–08:00/.test(l1cellOf('Петров', 6).textContent) && /СМ/.test(l1cellOf('Петров', 6).innerHTML));

/* ── 5. Слой 2 · Факт (примеры владельца, шаг 30; окно — всегда из кода Табеля, Q1) ── */
gotoLayer('l2');
check('L2: день по умолчанию 05.10', /5 октября 2026/.test($('#l2-navlabel').textContent));
check('L2: категории ДЯ/ДН — границы из настроек (замечание 2)', /Категории дневных кодов/.test($('#layer-l2').textContent));
check('L2: полоса дней 1..14', $$('#l2-days button').length === 14);
check('L2: метки интересных дней на 2, 5, 6, 12', [2, 5, 6, 12].every(n => $$('#l2-days button')[n - 1].querySelector('.dot')) && ![1, 9, 13].some(n => $$('#l2-days button')[n - 1].querySelector('.dot')));
let pr = rowOf('#l2-table tr', 'Петров');
check('пример 1 · Петров: окно 08:00–20:00 из кода Табеля «Я 10,75»', /08:00–20:00/.test(pr.cells[2].textContent));
check('пример 1 · Петров: план 12ч', pr.cells[3].textContent.trim() === '12ч', pr.cells[3].textContent);
check('пример 1 · Петров: отработано 11ч 30м', /11ч 30м/.test(pr.cells[4].textContent));
check('пример 1 · Петров: недоработка −30м', /−30м/.test(pr.cells[5].textContent));
check('пример 1 · Петров: переработка ДЯ 30м', /ДЯ 30м/.test(pr.cells[6].textContent));
check('пример 1 · Петров: отметки 07:30–19:30', /07:30–19:30/.test(pr.cells[1].textContent));
check('пример 1 · Петров: флаг РАННИЙ УХОД', /РАННИЙ УХОД/.test(pr.cells[7].textContent));
let iv = rowOf('#l2-table tr', 'Иванова');
check('пример 2 · Иванова: план 9ч', iv.cells[3].textContent.trim() === '9ч', iv.cells[3].textContent);
check('пример 2 · Иванова: отработано 8ч', iv.cells[4].textContent.trim() === '8ч', iv.cells[4].textContent);
check('пример 2 · Иванова: недоработка −1ч', /−1ч/.test(iv.cells[5].textContent));
check('пример 2 · Иванова: ДЯ 5ч и ДН 1ч', /ДЯ 5ч/.test(iv.cells[6].textContent) && /ДН 1ч/.test(iv.cells[6].textContent));
check('пример 2 · Иванова: отметки 08:00–12:00 + 13:00–23:00', /08:00–12:00/.test(iv.cells[1].textContent) && /13:00–23:00/.test(iv.cells[1].textContent));
check('пример 2 · Иванова: флагов нет', /нет/.test(iv.cells[7].textContent));
let sv = rowOf('#l2-table tr', 'Сидорова');
check('Сидорова: флаг ОПОЗДАНИЕ (08:25)', /ОПОЗДАНИЕ/.test(sv.cells[7].textContent));
check('Сидорова: недоработка −30м (округление 08:25→08:30)', /−30м/.test(sv.cells[5].textContent));
check('Сидорова: округление «→ 08:30–20:00»', /08:30–20:00/.test(sv.cells[1].textContent));

/* шаг 60 */
click($('#step-seg button[data-step="60"]'));
pr = rowOf('#l2-table tr', 'Петров');
check('шаг 60: отметки Петрова 07:30→08:00, 19:30→20:00 → отработано 12ч', pr.cells[4].textContent.trim() === '12ч', pr.cells[4].textContent);
check('шаг 60: недоработка и переработка исчезли', !/−30м/.test(pr.cells[5].textContent) && !/ДЯ/.test(pr.cells[6].textContent));
click($('#step-seg button[data-step="30"]'));
check('шаг 30: вернулось 11ч 30м', /11ч 30м/.test(rowOf('#l2-table tr', 'Петров').cells[4].textContent));

/* Q1 решён: ночная смена в Графике НЕ меняет окно и часы Табеля (Петров 06.10) */
click($('#l2-days button[data-day="6"]'));
pr = rowOf('#l2-table tr', 'Петров');
check('Q1 · Петров 06.10: окно по-прежнему 08:00–20:00 (из кода Табеля, не из Графика)', /08:00–20:00/.test(pr.cells[2].textContent));
check('Q1 · Петров 06.10: план 12ч, отработано 12ч — ночная смена на часы не повлияла', pr.cells[3].textContent.trim() === '12ч' && pr.cells[4].textContent.trim() === '12ч');
check('Q1 · Петров 06.10: недоработки и переработки нет', !/−/.test(pr.cells[5].textContent) && !/ДЯ|ДН/.test(pr.cells[6].textContent));
click($('#l2-days button[data-day="5"]'));

/* навигация по дням */
click($('#l2-days button[data-day="2"]'));
check('день 2: у Ивановой ДЯ 1ч 30м (08:30–19:00 при окне 09–18)', /ДЯ 1ч 30м/.test(rowOf('#l2-table tr', 'Иванова').cells[6].textContent));
click($('#l2-days button[data-day="12"]'));
check('день 12: у Ивановой недоработка −30м и РАННИЙ УХОД (17:40)', /−30м/.test(rowOf('#l2-table tr', 'Иванова').cells[5].textContent) && /РАННИЙ УХОД/.test(rowOf('#l2-table tr', 'Иванова').cells[7].textContent));
click($('#l2-next'));
check('кнопка «›» листает день (12 → 13)', /13 октября/.test($('#l2-navlabel').textContent));
click($('#l2-days button[data-day="5"]'));

/* ── 6. Слой 3 · Управленческий Табель ── */
gotoLayer('l3');
check('L3: бейдж «Период открыт»', /Период открыт/.test($('#l3-badge').textContent));
check('L3: сводка — банк Ивановой 1ч до закрытия', rowOf('#l3-summary tr', 'Иванова').textContent.includes('1ч'));
check('L3: превью — у Петрова 5.10 «недораб. 30м»', /недораб\. 30м/.test(l3cellOf('Петров', 5).textContent));
check('L3: превью — у Ивановой 5.10 ДЯ 5ч + ДН 1ч + недораб. 1ч', /ДЯ 5ч/.test(l3cellOf('Иванова', 5).textContent) && /ДН 1ч/.test(l3cellOf('Иванова', 5).textContent) && /недораб\. 1ч/.test(l3cellOf('Иванова', 5).textContent));
check('L3: превью — 2.10 у Ивановой ДЯ 1ч 30м', /ДЯ 1ч 30м/.test(l3cellOf('Иванова', 2).textContent));
click($('#l3-close'));
m = $('#modal-host .modal');
check('L3: модалка закрытия: банк оплатит 1ч (остаток 0ч)', /банк оплатит недоработку 1ч \(остаток 0ч\)/.test(m.textContent));
check('L3: модалка закрытия: каскад срежет 5.10 у Петрова', /каскад срежет переработки 5\.10/.test(m.textContent));
check('L3: модалка закрытия: перенос 30м у Сидоровой', rowOf('#modal-host .modal li', 'Сидорова') && /перенос на следующий период: 30м/.test(m.textContent));
click(m.querySelector('#close-ok'));
check('L3: бейдж «Период закрыт 15.10.2026»', /Период закрыт 15\.10\.2026/.test($('#l3-badge').textContent));
check('L3: банк Ивановой 1ч → 0ч', /1ч → 0ч/.test(rowOf('#l3-summary tr', 'Иванова').textContent));
check('L3: оплачено банком −1ч', /−1ч/.test(rowOf('#l3-summary tr', 'Иванова').textContent));
check('L3: у Петрова «срезано каскадом»', /срезано каскадом/.test(rowOf('#l3-summary tr', 'Петров').textContent));
check('L3: 5.10 Петров — chip «−30м каскад», ДЯ исчезла', /−30м каскад/.test(l3cellOf('Петров', 5).textContent) && !/ДЯ 30м/.test(l3cellOf('Петров', 5).textContent));
check('L3: 5.10 Иванова — «банк −1ч» + ДЯ 5ч + ДН 1ч остались', /банк −1ч/.test(l3cellOf('Иванова', 5).textContent) && /ДЯ 5ч/.test(l3cellOf('Иванова', 5).textContent) && /ДН 1ч/.test(l3cellOf('Иванова', 5).textContent));
check('L3: 12.10 Иванова — перенос «30м → след.»', /30м → след\./.test(l3cellOf('Иванова', 12).textContent));
check('L3: 5.10 Сидорова — перенос «30м → след.»', /30м → след\./.test(l3cellOf('Сидорова', 5).textContent));
check('L3: 7–9.10 Иванова — «ОТ» без начислений', l3cellOf('Иванова', 7).textContent.includes('ОТ') && !/ДЯ/.test(l3cellOf('Иванова', 7).textContent));
check('L3: кнопка «Закрыть» скрыта, «Открыть (демо)» видна', $('#l3-close').style.display === 'none' && $('#l3-reopen').style.display === '');
click($('#l3-reopen'));
check('L3: переоткрытие вернуло бейдж «Период открыт»', /Период открыт/.test($('#l3-badge').textContent));
check('L3: тост закрытия периода показан ранее', /Период закрыт\. Банк, каскад/.test(bodyText()));

/* ── 7. Схема ── */
gotoLayer('scheme');
const sch = $('#layer-scheme').textContent;
check('Схема: таблица 4 слоёв', ['0 · Табель', '1 · План / График', '2 · Факт', '3 · Управленческий Табель'].every(s => sch.includes(s)));
check('Схема: ссылки на движок', ['tabel_fill', 'schedule_view', 'evaluate_flags', 'day_card', 'mgmt_api', 'period_closings'].every(s => sch.includes(s)));
check('Схема: пример 1 — 12ч / 11ч 30м / 30м', /12ч/.test(sch) && /11ч 30м/.test(sch));
check('Схема: пример 2 — ДЯ 5ч + ДН 1ч, банк 1ч → 0', /ДЯ 5ч \+ ДН 1ч/.test(sch) && /1ч → 0/.test(sch));
check('Схема: вопросы Q1–Q9 со статусами ✅', ['Q1', 'Q2', 'Q3', 'Q4', 'Q5', 'Q6', 'Q7', 'Q8', 'Q9']
  .every(q => new RegExp(q + '\\. ✅').test($('#layer-scheme').innerHTML)));
check('Схема: Q1 — решён, переключателя режима нет', /Q1 — решён/.test(sch) && !/Главное противоречие/.test(sch));
check('Схема: «недопуск» не добавляется (замечание 1 / Q6)', /Не добавляется/.test(sch));
check('Схема: ДЯ/ДН — из настроек «Категории дневных кодов» (замечание 2)', /Категории дневных кодов/.test(sch));
check('Схема: упрощения перечислены', /Упрощения прототипа/.test(sch));

/* ── 8. Финал ── */
check('нет ошибок JS за весь прогон', errors.length === 0, errors.join(' | '));
console.log('—'.repeat(50));
console.log((fails ? '❌ ' + fails + ' из ' + total + ' провалено' : '✅ все ' + total + ' проверок пройдены'));
process.exit(fails ? 2 : 0);
