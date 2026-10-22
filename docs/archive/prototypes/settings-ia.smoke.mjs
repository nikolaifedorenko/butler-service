/* Смоук концепта «Единый центр настроек» в jsdom: обход экранов кликами,
   проверка прав-видимости, deep-link'ов и ошибок консоли.

   Запуск (нужен jsdom из butler-service):
     cd butler-service && npm install
     node docs/prototypes/settings-ia.smoke.mjs
   Код возврата: 0 — все проверки пройдены, 2 — есть провалы. */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { JSDOM, VirtualConsole } from 'jsdom';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const errors = [];
const vc = new VirtualConsole();
vc.on('jsdomError', e => errors.push('[jsdomError] ' + String(e.stack || e.message).split('\n')[0]));
vc.on('error', (...a) => errors.push('[console.error] ' + a.map(String).join(' ')));

const html = fs.readFileSync(path.join(HERE, 'settings-ia.html'), 'utf8');
const dom = new JSDOM(html, { url: 'http://localhost/', runScripts: 'dangerously',
  pretendToBeVisual: true, virtualConsole: vc });
const { window } = dom;
window.Element.prototype.scrollTo = function () {};
window.HTMLElement.prototype.scrollIntoView = function () {};

const $ = s => window.document.querySelector(s);
const $$ = s => [...window.document.querySelectorAll(s)];
const txt = s => ($(s)?.textContent || '').replace(/\s+/g, ' ').trim();
const has = (s, sub) => txt(s).includes(sub);
const click = el => { if (!el) throw new Error('нет элемента для клика: ' + el); el.dispatchEvent(new window.MouseEvent('click', { bubbles: true })); };
const byText = (sel, sub) => $$(sel).find(b => (b.textContent || '').includes(sub));


let pass = 0, fail = 0;
function check(name, cond, extra = '') {
  if (cond) { pass++; console.log(`  ✓ ${name}`); }
  else { fail++; console.log(`  ❌ ${name}${extra ? ' — ' + extra : ''}`); }
}

/* ── 1. старт: менеджер, компьютер, Настройки → Обзор ── */
console.log('1. Старт (менеджер, компьютер)');
check('меню без «Прав доступа» и «Журнала аудита» (7 пунктов максимум)',
  $$('#sidenav [data-view]').length === 7 && !byText('#sidenav [data-view]', 'Права доступа'));
check('под-навигация настроек: группа «Объект»', has('.settings-nav', 'Объект'));
check('под-навигация: «Ночной обход» и «Электрокары» — новые экраны',
  !!byText('[data-st]', 'Ночной обход') && !!byText('[data-st]', 'Электрокары'));
check('группа «Администрирование»: менеджер видит Аудит, но не Права (нет access.manage)',
  has('.settings-nav', 'Администрирование') && !!byText('[data-st]', 'Журнал аудита') && !byText('[data-st]', 'Права доступа'));
check('«Обзор»: новые health-проверки справочников',
  has('#st-body', 'APP-NIGHT-ZONE-NO-TEMPLATE') && has('#st-body', 'APP-SVC-NO-CHANNEL'));

/* ── 2. Ночной обход: master-detail ── */
console.log('2. Настройки → Ночной обход (менеджер)');
click(byText('[data-st]', 'Ночной обход'));
check('hash-адрес экрана', window.location.hash === '#/settings/night', window.location.hash);
check('список зон слева', has('.md-list', 'Виллы') && has('.md-list', 'Без зоны'));
check('плашка «со следующей смены»', has('#st-body', 'применяются со следующей смены'));
check('шаблон чек-листа зоны с пунктами и службами', has('#st-body', 'Двери и окна закрыты') && has('#st-body', 'Служба безопасности'));
click(byText('[data-zone]', 'Пляж'));
check('зона с пустым шаблоном показывает подсказку', has('#st-body', 'Шаблон пуст'));
click(byText('[data-zone]', 'Виллы'));
click(byText('[data-area-open]', 'Вилла 4001'));
check('карточка объекта: индивидуальный пункт', has('#st-body', 'Сейф: сверить код виллы 4001'));
click($('#area-back'));
check('возврат к зоне', has('#st-body', 'Объекты зоны'));
click(byText('[data-stab]', 'Службы'));
check('вкладка «Службы»: таблица с каналами доставки', has('#st-body', 'Ответственные службы') && has('#st-body', 'Housekeeping · чат'));

/* правка чек-листа менеджером */
click(byText('[data-stab]', 'Обход'));
const ziAdd = $('#zi-add');
check('кнопка «+ Пункт» доступна менеджеру', !!ziAdd);
if (ziAdd) {
  click(ziAdd);
  const m = $('.modal-backdrop');
  check('модалка пункта открылась', !!m && has('.modal-head', 'Новый пункт шаблона'));
  if (m) {
    m.querySelector('#i-text').value = 'Тестовый пункт смоука';
    click(m.querySelector('[data-s]'));
    check('пункт добавлен в шаблон', has('#st-body', 'Тестовый пункт смоука'));
  }
}

/* ── 3. Электрокары: парк и места ── */
console.log('3. Настройки → Электрокары (менеджер)');
click(byText('[data-st]', 'Электрокары'));
check('парк: таблица каров', has('#st-body', 'CAR-01') && has('#st-body', 'CAR-06'));
check('места стоянки: чипы и удаление', has('#st-body', 'Парковка у корпуса А') && !!$('[data-locdel]'));
click($('[data-locdel]'));   /* Парковка у корпуса А — занята CAR-01 */
check('удаление занятого места → 409-подсказка', $$('.toast').some(t => t.textContent.includes('409')));
$('#loc-new').value = 'Парковка у корпуса B';
click($('#loc-add'));
check('новое место добавлено', has('#st-body', 'Парковка у корпуса B'));
click($('#car-add'));
const cm = $('.modal-backdrop');
check('модалка «Новый кар» без места стоянки (решение 18.10)', !!cm && has('.modal-head', 'без места стоянки'));
if (cm) { cm.querySelector('#c-no').value = 'CAR-07'; click(cm.querySelector('[data-s]'));
  check('кар добавлен в парк', has('#st-body', 'CAR-07')); }

/* ── 4. deep-link'и из операционных разделов ── */
console.log('4. Deep-link из операционных разделов');
click(byText('#sidenav [data-view]', 'Ночной отчёт'));
check('в разделе есть кнопка «Справочник ↗» (менеджер)', !!$('#night-dict'));
click($('#night-dict'));
check('переход в Настройки → Ночной обход', window.location.hash === '#/settings/night', window.location.hash);
click(byText('#sidenav [data-view]', 'Электрокары'));
check('в разделе есть «+ Кар ↗» и «Места ↗»', !!$('#cars-add') && !!$('#cars-loc'));
click($('#cars-loc'));
check('переход в Настройки → Электрокары', window.location.hash === '#/settings/cars', window.location.hash);

/* ── 5. батлер: телефон, операции, никаких правок ── */
console.log('5. Батлер (телефон)');
click(byText('#role-seg button', 'Батлер'));
check('устройство переключилось на телефон', !$('#app-phone').classList.contains('hidden'));
check('стартовый экран — «Мои отметки»', $('#ph-body').textContent.includes('Пришёл'));
check('tabbar: ровно 5 разделов батлера', $$('#ph-tabs button').length === 5);
click(byText('#ph-tabs button', 'Ночной отчёт'));
check('нет кнопки «Справочник» (нет night.edit)', !$('#night-dict') && has('#ph-body', 'только просмотр'));
click(byText('#ph-tabs button', 'Электрокары'));
check('нет «+ Кар» и «Места» (нет cars.manage)', !$('#cars-add') && !$('#cars-loc'));
check('кнопка «Взять» на свободном каре есть (cars.use)', $$('#ph-body [data-stub]').some(b => b.textContent.includes('Взять')));

/* отметка «Пришёл» */
click(byText('#ph-tabs button', 'Мои отметки'));
click($('#me-in'));
check('после отметки — «Вы на работе» и кнопка «Ушёл»', has('#ph-body', 'Вы на работе') && !!$('#me-out'));

/* ── 6. песочница прав ── */
console.log('6. Песочница прав (батлер + settings.view/night.view/night.edit)');
click($('#btn-sandbox'));
const sb = $('.modal-backdrop');
check('модалка песочницы открылась', !!sb && has('.modal-head', 'Песочница прав'));
for (const key of ['settings.view', 'night.view', 'night.edit']) {
  const ch = sb.querySelector(`[data-perm="${key}"]`);
  if (ch && !ch.checked) { ch.checked = true; ch.dispatchEvent(new window.Event('change', { bubbles: true })); }
}
click(sb.querySelector('[data-done]'));
click(byText('#dev-seg button', 'Компьютер'));
check('меню батлера с выданными правами содержит «Настройки»', !!byText('#sidenav [data-view]', 'Настройки'));
click(byText('#sidenav [data-view]', 'Настройки'));
check('экран «Ночной обход» доступен батлеру с night.edit', !!byText('[data-st]', 'Ночной обход'));
click(byText('[data-st]', 'Ночной обход'));
check('правка доступна (есть «+ Пункт»)', !!$('#zi-add'));
click($('#btn-sandbox'));
const sb2 = $('.modal-backdrop');
const chEdit = sb2.querySelector('[data-perm="night.edit"]');
chEdit.checked = false; chEdit.dispatchEvent(new window.Event('change', { bubbles: true }));
click(sb2.querySelector('[data-done]'));
click(byText('[data-st]', 'Обзор')); click(byText('[data-st]', 'Ночной обход'));
check('без night.edit — только просмотр, «+ Пункт» исчез', !$('#zi-add') && has('#st-body', 'night.edit'));

/* ── 7. супервайзер: ключевой сценарий (не потерял чек-листы) ── */
console.log('7. Супервайзер');
click(byText('#role-seg button', 'Супервайзер'));
click(byText('#sidenav [data-view]', 'Настройки'));
click(byText('[data-st]', 'Ночной обход'));
check('супервайзер правит чек-листы (night.edit по умолчанию)', !!$('#zi-add'));
check('но «Электрокары» — только просмотр (нет cars.manage): «+ Кар» отсутствует',
  (click(byText('[data-st]', 'Электрокары')), !$('#car-add')));
check('«Расчёт» виден, но без правки (нет settings.edit)',
  (click(byText('[data-st]', 'Расчёт')), has('#st-body', 'без изменений')));

/* ── 7b. админ: Права доступа в Администрировании ── */
click(byText('#role-seg button', 'Админ'));
click(byText('#sidenav [data-view]', 'Настройки'));
check('админ видит «Права доступа» в группе «Администрирование»', !!byText('[data-st]', 'Права доступа'));

/* ── 8. заметки и подсказки ── */
console.log('8. Заметки концепта');
click($('#btn-notes'));
check('модалка заметок: 9 пунктов предложений', $$('.modal-backdrop .item-row').length >= 9);
click($('.modal-backdrop [data-ok]'));
click($('#btn-hints'));
check('подсказки концепта скрываются', $$('.pnote').length === 0);
click($('#btn-hints'));

/* ── 9. чистота консоли ── */
console.log('9. Консоль');
check('нет ошибок консоли за весь сценарий', errors.length === 0, errors.slice(0, 3).join(' | '));

console.log(`\nИтог: ${pass} пройдено, ${fail} провалено`);
process.exit(fail ? 2 : 0);
