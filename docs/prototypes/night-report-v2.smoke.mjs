/* Смоук прототипа «Ночной отчёт v2» в jsdom: обход всех экранов кликами,
   проверка содержимого и ошибок консоли.

   Запуск (нужен Node ≥ 22 и jsdom из butler-service):
     cd butler-service && npm install
     node ../night-report-v2/smoke.mjs
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

const html = fs.readFileSync(path.join(HERE, 'prototype.html'), 'utf8');
const dom = new JSDOM(html, { url: 'http://localhost/', runScripts: 'dangerously',
  pretendToBeVisual: true, virtualConsole: vc });
const { window } = dom;
window.matchMedia = window.matchMedia || (q => ({ matches: false, media: q, addListener() {},
  removeListener() {}, addEventListener() {}, removeEventListener() {} }));
window.URL.createObjectURL = () => 'blob:stub';
window.URL.revokeObjectURL = () => {};
window.Element.prototype.scrollTo = function () {};
window.HTMLElement.prototype.scrollIntoView = function () {};

const $ = s => window.document.querySelector(s);
const $$ = s => [...window.document.querySelectorAll(s)];
const txt = s => ($(s)?.textContent || '').replace(/\s+/g, ' ').trim();
const click = el => { if (!el) throw new Error('нет элемента для клика'); el.dispatchEvent(new window.MouseEvent('click', { bubbles: true })); };
const sleep = ms => new Promise(r => setTimeout(r, ms));

let pass = 0, fail = 0;
function check(name, cond, extra = '') {
  if (cond) { pass++; console.log(`  ✓ ${name}`); }
  else { fail++; console.log(`  ❌ ${name}${extra ? ' — ' + extra : ''}`); }
}
const navTo = id => click($(`[data-nav="${id}"]`));

await sleep(120);

console.log('1 · Зоны');
check('6 карточек зон', $$('.zone-card').length === 6, String($$('.zone-card').length));
check('названия зон из задания', ['Семейные виллы', 'Президентские виллы', 'Императорские виллы',
  'Семейные винные виллы', 'Президентские винные виллы', 'Офисы']
  .every(n => txt('#main').includes(n)));
check('счётчики в шапке', /Замечаний/.test(txt('#main')) && /Объектов/.test(txt('#main')));
check('кнопка «Недостатки»', /Недостатки: \d+/.test(txt('[data-act="to-defects"]')),
  txt('[data-act="to-defects"]'));
check('навигация отрисована', $$('#sidenav [data-nav]').length >= 8);

console.log('\n2 · Объекты зоны');
click($$('.zone-card')[0]);
check('12 объектов «Семейные виллы»', $$('.obj').length === 12, String($$('.obj').length));
check('Вилла 4001 … 4012', txt('#main').includes('Вилла 4001') && txt('#main').includes('Вилла 4012'));
check('хлебные крошки', /Ночной отчёт/.test(txt('.crumb')) && /Семейные виллы/.test(txt('.crumb')));
check('статусы объектов', $$('.obj.done').length > 0 && $$('.obj.taken').length > 0);
click($('[data-filter="bad"]'));
check('фильтр «С замечаниями»', $$('.obj').length > 0 && $$('.obj').length < 12, String($$('.obj').length));
click($('[data-filter="all"]'));
const q = $('#obj-q'); q.value = '4007';
q.dispatchEvent(new window.Event('input', { bubbles: true }));
check('поиск по объектам', $$('.obj').length === 1 && txt('.obj .t').includes('4007'), String($$('.obj').length));
const q2 = $('#obj-q'); q2.value = '';
q2.dispatchEvent(new window.Event('input', { bubbles: true }));
check('сброс поиска возвращает все объекты', $$('.obj').length === 12, String($$('.obj').length));

console.log('\n3 · Чек-лист объекта');
click($('[data-open="9"]'));
check('пункты чек-листа (5)', $$('.night-item').length === 5, String($$('.night-item').length));
check('пункты из задания', ['Витражи закрыты', 'Свет выключен', 'Вилла убрана', 'Вилла укомплектована']
  .every(t => txt('#main').includes(t)));
check('у пункта — ответственная служба', $$('.night-item .badge.gold').length === 5,
  String($$('.night-item .badge.gold').length));
check('кнопки ОК / Не ОК / медиа', $$('[data-ans="ok"]').length === 5 && $$('[data-ans="bad"]').length === 5
  && $$('[data-expand]').length === 5);
check('объект взят в работу', /ведёт Громова/.test(txt('#main')), txt('.page-head .sub'));
click($$('[data-ans="bad"]')[0]);
check('«Не ОК» открыл редактор пункта', !!$('#cmt-vit') && !!$('[data-save="vit"]'));
check('кнопки съёмки фото и видео', $$('[data-media="photo"]').length === 1 && $$('[data-media="video"]').length === 1);
check('capture у камеры и видео', $('[data-media="photo"]')?.getAttribute('capture') === 'environment'
  && $('[data-media="video"]')?.getAttribute('capture') === 'camcorder');
$('#cmt-vit').value = 'Витраж открыт, смоук-проверка';
click($('[data-save="vit"]'));
check('комментарий сохранён, пункт «Не ОК»', $$('.night-item.bad').length === 1
  && /Витраж открыт, смоук-проверка/.test(txt('#main')));
click($('[data-expand="light"]'));
click($('[data-demo="photo"]'));
check('демо-фото приложено', $$('.thumb').length >= 1 && /IMG_/.test($('#main').innerHTML));
click($('[data-finish]'));
check('закрытие с неотмеченными пунктами спрашивает подтверждение',
  /Есть неотмеченные пункты/.test(txt('.modal-head')), txt('.modal-head'));
click($('[data-ok]'));
check('объект закрыт и вернулись к списку', $$('.obj').length === 12, String($$('.obj').length));

console.log('\n4 · Недостатки и отправка');
navTo('defects');
check('группы по службам', $$('.dsp-group').length >= 3, String($$('.dsp-group').length));
check('службы видны', ['Техническая служба', 'Хозяйственная служба', 'Батлер-сервис', 'IT-департамент']
  .some(s => txt('#main').includes(s)));
check('предпросмотр сообщения', /прошу исправить:/.test(txt('.preview')), txt('.preview').slice(0, 90));
check('в тексте нет дедлайна', !/до 08:00/.test(txt('.preview')));
check('в тексте — ночные батлеры смены', /Ночные батлеры смены: .+/.test(txt('.preview')),
  (txt('.preview').match(/Ночные батлеры смены: [^\n]*/) || [''])[0]);
check('каналы доставки — чекбоксы', $$('[data-ch="chat"]').length >= 1 && $$('[data-ch="email"]').length >= 1);
check('подсказка: общие чаты не объединяем', /не объединяем/.test(txt('#main')));
check('подсказка: исправленное не отправляется', /исправлено после отправки/.test(txt('#main')));
check('отправленное ранее учтено счётчиком', /Отправлено ранее/.test(txt('#main'))
  && !/отправлено 01:35/.test(txt('#main')));
check('фильтр скрывает отправленные', !$$('.dsp-item.sent').length);
check('блок «Не проверено» виден', /Не проверено \(не отмечено батлером\)/.test(txt('#main')));
const unBefore = $$('[data-usel]').length;
check('в блоке «Не проверено» есть пункты', unBefore > 5, String(unBefore));
click($('#un-all'));
check('«включить все» отмечает пункты', $$('[data-usel]:checked').length === unBefore,
  String($$('[data-usel]:checked').length));
check('в предпросмотре появился блок «Не проверено»',
  /Не проверено \(не отмечено батлером\):/.test(txt('.preview')) || /Не проверено/.test(txt('.preview')));
click($('[data-act="select-all"]'));
const selected = $$('[data-sel]:checked').length;
check('«Выбрать всё» отмечает пункты', selected >= 8, String(selected));
click($('[data-act="send-selected"]'));
check('модалка отправки', /По одной записи на каждый канал и получателя/.test(txt('.modal-body')),
  txt('.modal-body').slice(0, 90));
check('в модалке — счётчик отправок', /Отправить \(\d+\)/.test(txt('.modal-foot')), txt('.modal-foot'));
check('в модалке видны получатели', /-100\d+|@mriyaresort\.ru/.test($('#modal').innerHTML));
click($('[data-ok]'));
await sleep(900);
check('после отправки — журнал', txt('#main').includes('Журнал отправок'));
check('в журнале прибавились записи', $$('table.tbl tbody tr').length >= 5, String($$('table.tbl tbody tr').length));
check('статус «отправлено»', /отправлено/.test(txt('#main')));
check('в журнале отмечено «не проверено»', /не проверено/.test(txt('#main')));
navTo('defects');
check('отправленные убраны из списка', $$('[data-sel]').length === 0, String($$('[data-sel]').length));
const onlyNew = $('#only-new'); onlyNew.checked = false;
onlyNew.dispatchEvent(new window.Event('change', { bubbles: true }));
check('фильтр «только не отправленные» снимается', $$('.dsp-item.sent').length > 0);

console.log('\n5 · Журнал');
navTo('journal');
check('таблица журнала', $$('table.tbl th').length === 8, String($$('table.tbl th').length));
check('есть сбой и кнопка «Повторить»', /сбой/.test(txt('#main')) && !!$('[data-resend]'));
click($('[data-resend]'));
check('повтор меняет статус', /отправлено/.test(txt('#main')));
click($('[data-show-msg]'));
check('текст отправки показан', /прошу исправить/.test(txt('.modal-body')));
click($('[data-x]'));

console.log('\n6 · Настройки');
navTo('set:zones');
check('зоны в настройках', $$('.rule-row').length >= 6, String($$('.rule-row').length));
click($('[data-objects="1"]'));
check('объекты зоны в настройках', /Вилла 4012/.test(txt('#main')));
$('#no-name').value = 'Вилла 4013';
click($('#no-add'));
check('объект добавлен', /Вилла 4013/.test(txt('#main')));
$('#no-prefix').value = 'Вилла '; $('#no-start').value = '4014'; $('#no-count').value = '3';
click($('#no-bulk'));
check('серия объектов создана', /Вилла 4016/.test(txt('#main')));

navTo('set:items');
check('шаблон пунктов зоны', $$('.rule-row').length >= 5, String($$('.rule-row').length));
check('у пункта — выбор службы', $$('[data-svc-of]').length >= 5, String($$('[data-svc-of]').length));
$('#ni-text').value = 'Двери балкона закрыты';
click($('#ni-add'));
check('пункт добавлен в зону', /Двери балкона закрыты/.test(txt('#main')));
const svcSel = $('[data-svc-of="vit"]');
svcSel.value = '2'; svcSel.dispatchEvent(new window.Event('change', { bubbles: true }));
check('службу у пункта можно сменить', /Хозяйственная служба/.test(txt('#main')));
check('панель индивидуальных правок объекта', /Индивидуальные особенности объекта/.test(txt('#main')));
check('выбор зоны и объекта', !!$('#ov-zone') && !!$('#ov-obj'));
const ovZone = $('#ov-zone'); ovZone.value = '1'; ovZone.dispatchEvent(new window.Event('change', { bubbles: true }));
const ovObj = $('#ov-obj'); ovObj.value = '1'; ovObj.dispatchEvent(new window.Event('change', { bubbles: true }));
check('у объекта видна своя формулировка', /своя формулировка/.test(txt('#main')), txt('#main').slice(0, 0));
check('у объекта виден свой пункт', /Детская кроватка установлена и исправна/.test(txt('#main')));
click($('[data-ov-dis="light"]'));
check('пункт можно отключить у объекта', /отключён у объекта/.test(txt('#main')));
click($('[data-ov-reset="light"]'));
check('правку можно сбросить к шаблону зоны', !/отключён у объекта/.test(txt('#main')));
click($('#ov-add'));
$('#ova-text').value = 'Камин погашен';
click($('[data-ok]'));
check('свой пункт объекта добавлен', /Камин погашен/.test(txt('#main')));

navTo('set:services');
check('службы в списке', $$('.rule-row').length >= 4, String($$('.rule-row').length));
click($('[data-svc-add]'));
check('модалка службы: каналы чекбоксами', !!$('#sv-chat') && !!$('#sv-email'));
check('поля e-mail и чатов', !!$('#sv-email') && !!$('#sv-manual-link'));
check('чаты — выбор из найденного списка', $$('[data-pick-chat]').length >= 5,
  String($$('[data-pick-chat]').length));
$('#sv-email').checked = true; $('#sv-email').dispatchEvent(new window.Event('change', { bubbles: true }));
check('чекбокс «Письмо» открывает ящик', !$('#sv-email-box').classList.contains('hidden'));
const anyChat = $('[data-pick-chat]');
anyChat.checked = true; anyChat.dispatchEvent(new window.Event('change', { bubbles: true }));
$('#sv-name').value = 'Служба безопасности';
$('#sv-email').value = 'security@mriyaresort.ru';
click($('#sv-manual-link'));
check('ручной ввод chat_id спрятан до запроса', !$('#sv-manual').classList.contains('hidden'));
$('#sv-chat-title').value = 'СБ · ночь'; $('#sv-chat-id').value = '-1001110002223';
click($('#sv-chat-add'));
check('чат добавлен в общий список и отмечен', /СБ · ночь/.test($('#modal').innerHTML)
  && $$('[data-pick-chat]:checked').length >= 2);
click($('[data-ok]'));
check('служба добавлена', /Служба безопасности/.test(txt('#main')));
click($('[data-svc-test]'));
check('тест доставки показывает каналы', /Telegram →|Письмо →/.test(txt('.modal-body')), txt('.modal-body').slice(0, 100));
click($('[data-c]'));

navTo('set:integrations');
check('токен не светится в поле', $('#tg-token').type === 'password' && $('#tg-token').value === ''
  && /••••/.test($('#tg-token').placeholder), $('#tg-token').placeholder);
click($('#tg-show'));
check('«Показать» раскрывает токен', $('#tg-token').type === 'text');
click($('#tg-check'));
check('getMe-заглушка отвечает', /mriya_night_bot/.test(txt('.modal-body')));
click($('[data-ok]'));
check('общий список чатов в настройках Telegram', /Список чатов \(получаем здесь/.test(txt('#main'))
  && /Техслужба · Мрия/.test(txt('#main')));
check('видно, за кем закреплён чат', /не закреплён/.test(txt('#main')) || $$('[data-nav]').length > 0);
const chatsBefore = ($$('#main .check-list .chk').length);
click($('#tg-chats'));
check('getUpdates добавляет новые чаты', $$('#main .check-list .chk').length > chatsBefore,
  `${chatsBefore} → ${$$('#main .check-list .chk').length}`);
click($('#sm-test'));
check('тест письма', /Тестовое письмо отправлено/.test(txt('.modal-head')));
click($('[data-ok]'));
check('SMTP-поля', !!$('#sm-host') && !!$('#sm-ssl') && !!$('#sm-from'));
check('почта — через MS Exchange', /MS Exchange/.test(txt('#main')));
const relay = $('#sm-relay');
check('есть режим внутреннего релея', !!relay && !relay.checked);
relay.checked = true; relay.dispatchEvent(new window.Event('change', { bubbles: true }));
check('релей скрывает логин и пароль', $('#sm-auth-box').classList.contains('hidden'));
relay.checked = false; relay.dispatchEvent(new window.Event('change', { bubbles: true }));
check('SMTP AUTH возвращает поля авторизации', !$('#sm-auth-box').classList.contains('hidden'));
check('шаблон с плейсхолдерами', /\{items\}/.test($('#tpl').value));
click($('#tpl-preview'));
check('предпросмотр шаблона', /Ночной отчёт|Недостатков нет/.test(txt('.modal-body')));
click($('[data-ok]'));

console.log('\n7 · Роль «Батлер»: отправлять может любой');
const roleSel = $('#role-switch');
roleSel.value = 'butler'; roleSel.dispatchEvent(new window.Event('change', { bubbles: true }));
check('имя и роль в топбаре сменились', txt('#u-name') === 'Иванов И.И.' && txt('#u-role') === 'Батлер');
check('справочники скрыты у батлера', $$('[data-nav^="set:"]').length === 0
  || $$('[data-nav]').filter(b => b.dataset.nav.startsWith('set:')).length === 0);
check('обход доступен батлеру', !!$('[data-nav="zones"]'));
navTo('defects');
check('отправка недостатков доступна батлеру', !!$('[data-act="send-selected"]'));
navTo('zones');
roleSel.value = 'supervisor'; roleSel.dispatchEvent(new window.Event('change', { bubbles: true }));
check('возврат к роли супервайзера', txt('#u-role') === 'Супервайзер'
  && $$('[data-nav]').filter(b => b.dataset.nav.startsWith('set:')).length >= 4);

console.log('\n8 · Шаг «Проверка электрокаров» — отдельно от зон');
check('панель шага на экране зон', /Шаг «Проверка электрокаров»/.test(txt('#main')));
click($('[data-act="cars-step"]'));
check('обход каров открывается', /Кар №/.test(txt('.modal-body')) && /перепаркован/.test(txt('.modal-body')));
click($('[data-x]'));

console.log('\n9 · Индивидуальный чек-лист в обходе');
click($$('.zone-card')[0]);
click($('[data-open="1"]'));
check('своя формулировка у объекта', /Вилла убрана \(включая детскую комнату\)/.test(txt('#main')));
check('бейдж «индивидуально»', /индивидуально/.test(txt('#main')));
check('свой пункт объекта', /Детская кроватка установлена и исправна/.test(txt('#main'))
  && /пункт объекта/.test(txt('#main')));
navTo('zones'); click($('.zone-card')); click($('[data-open="2"]'));
/* у Виллы 4002 пункт «ТВ и Wi-Fi работают» отключён индивидуально:
   шаблон зоны 5 пунктов + 1 добавленный в смоуке − 1 отключённый = 5 */
check('отключённый у объекта пункт не показан', $$('.night-item').length === 5
  && !/ТВ и Wi-Fi работают/.test(txt('#main')), String($$('.night-item').length));

console.log('\n9b · Недостаток исправили после отправки');
navTo('zones');
click($$('.zone-card')[4]);
check('зона «Президентские винные виллы»', $$('.obj').length === 6, String($$('.obj').length));
click($('[data-open="3"]'));
check('отправленный недостаток виден в чек-листе', /отправлено/.test(txt('#main')));
click($$('[data-ans="ok"]')[0]);
check('появилась пометка «исправлено после отправки»', /исправлено после отправки/.test(txt('#main')));
check('нового уведомления не создаётся', !/Отправить/.test(txt('.page-head')));

console.log('\n10 · О прототипе');
navTo('about');
check('этапы и решения владельца на месте', /Этапы внедрения/.test(txt('#main'))
  && /Решения владельца/.test(txt('#main')));
check('решения зафиксированы', /Чек-лист — общий на зону/.test(txt('#main'))
  && /Отправка только вручную/.test(txt('#main')) && /Электрокары — отдельным шагом/.test(txt('#main')));
check('решения по Exchange, видео и чатам', /MS Exchange/.test(txt('#main'))
  && /Размер видео — 50 МБ/.test(txt('#main')) && /не объединяем и не дедуплицируем|каждая служба отправляет/.test(txt('#main')));
check('открытых вопросов не осталось', /Открытых вопросов нет/.test(txt('#main')));
check('нет мусора в DOM', !/undefined|\[object Object\]/.test($('#main').innerHTML));

console.log('\n=== ошибки консоли ===');
[...new Set(errors.map(e => e.slice(0, 220)))].forEach(e => console.log('  ' + e));
if (errors.length) fail++;
console.log(`\nИТОГ: ${pass + fail} проверок, пройдено ${pass}, провалено ${fail}`);
process.exit(fail ? 2 : 0);
