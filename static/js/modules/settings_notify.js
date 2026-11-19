/* Раздел «Настройки»: экран «Чаты и Почта».
   Оболочка, черновик версии справочников и общие помощники — в settings.js.
   Модуль на lit-html (ADR-0013, раздел 7). */
'use strict';

import { registerModule } from '../app.js';
import { $, api, closeModal, confirmDialog, dateRu, downloadBlob, openModal, toast } from '../core.js';
import { html, mount, nothing, render } from '../ui/html.js';
import { settingsGo, settingsHeadView, settingsPanelView } from './settings.js';

registerModule({ screens: { notify: { render: settingsScreenNotify, icon: 'mail' } } });

/* ══════════════════════════════════════════════════════════════════
   ЧАТЫ И ПОЧТА — общие настройки доставки (Telegram и MS Exchange)
   ══════════════════════════════════════════════════════════════════ */
/* Доставка — общая функциональность приложения, а не принадлежность ночного
   отчёта: здесь токены и учётные данные (одни на всё приложение), каталог чатов
   Telegram и шаблоны сообщений по разделам. Разделы подключаются к доставке со
   своими получателями (ночной отчёт — ответственные службы) и своим шаблоном.
   Право settings.edit: в экране токены и пароли. */
const NOTIFY_CONSUMERS = [
  { area: 'Ночной отчёт', what: 'недостатки смены по ответственным службам', to: 'службы: чат и/или письмо', on: true },
  { area: 'Электрокары', what: 'замечания при возврате кара, «кар не найден»', to: 'служба парка, супервайзер', on: false },
  { area: 'График и Табель', what: 'заявления сотрудников, закрытие периода', to: 'руководитель, HR', on: false },
  { area: 'Отметки', what: 'опоздания и пропущенные отметки за смену', to: 'руководитель смены', on: false },
];
let notifyDomain = 'night';

async function settingsScreenNotify(host) {
  let data;
  try { data = await api('/api/notify/config'); }
  catch (e) {
    render(html`${settingsHeadView('Чаты и Почта', '')}<div class="empty">${e.message}</div>`, mount(host));
    return;
  }
  const cfg = data.config || {};
  const tg = cfg.telegram || {}, em = cfg.email || {}, ready = cfg.ready || {};
  /* секреты в БД зашифрованы ключом NOTIFY_SECRET_KEY: ключ потерян или сменился —
     сервер не может их прочитать и просит ввести заново
*/
  const unreadable = new Set(cfg.unreadable || []);
  const reenter = html`<small class="hint" style="color:var(--danger)">не расшифровывается: ключ шифрования сменился — введите заново</small>`;
  const chats = data.chats || [];
  let tpls = [];
  try { tpls = (await api('/api/notify/templates')).templates || []; } catch { tpls = []; }
  if (!tpls.some(t => t.domain === notifyDomain)) notifyDomain = (tpls[0] || {}).domain || 'night';
  const tpl = tpls.find(t => t.domain === notifyDomain) || { text: '', placeholders: [] };
  const again = () => settingsScreenNotify(host);

  const saveTelegram = async () => {
    const body = { notify_telegram_api: $('#nt-api', host).value.trim() };
    const token = $('#nt-token', host).value.trim();
    if (token) body.notify_telegram_token = token;      // пустое поле = «не менять»
    try {
      const r = await api('/api/notify/config', { method: 'PUT', body });
      toast(`Настройки Telegram сохранены${r.changed.length ? ` (${r.changed.length})` : ''}`, 'ok');
      again();
    } catch (e) { toast(e.message, 'err'); }
  };
  const checkBot = async () => {
    const out = $('#nt-result', host);
    out.textContent = 'проверяем…';
    try {
      // таймаут канала в настройках — до 300 с, обычные 20 с клиента обрывали бы проверку (UI-03)
      const r = await api('/api/notify/telegram/check', { method: 'POST', timeout: 300000,
        body: { token: $('#nt-token', host).value.trim(), api: $('#nt-api', host).value.trim() } });
      out.textContent = `бот: @${r.bot.username || '—'} (${r.bot.first_name || ''})`;
      toast('Токен принят Telegram', 'ok');
    } catch (e) { out.textContent = ''; toast(e.message, 'err'); }
  };
  const refreshChats = async () => {
    try {
      const r = await api('/api/notify/telegram/chats', { method: 'POST' });
      toast(`Каталог обновлён: найдено ${r.seen}, добавлено ${r.added}`, 'ok');
      again();
    } catch (e) { toast(e.message, 'err'); }
  };
  const testChat = async c => {
    try {
      await api('/api/notify/telegram/test', { method: 'POST', body: { chat_id: Number(c.chat_id) } });
      toast('Тестовое сообщение отправлено в чат', 'ok');
    } catch (e) { toast(e.message, 'err'); }
  };
  const saveMail = async () => {
    const body = {
      notify_smtp_host: $('#ne-host', host).value.trim(), notify_smtp_port: $('#ne-port', host).value.trim(),
      notify_smtp_security: $('#ne-sec', host).value, notify_smtp_user: $('#ne-user', host).value.trim(),
      notify_email_from: $('#ne-from', host).value.trim(), notify_email_reply_to: $('#ne-reply', host).value.trim(),
      notify_timeout: $('#ne-timeout', host).value.trim(),
    };
    const pass = $('#ne-pass', host).value;
    if (pass) body.notify_smtp_password = pass;          // пустое поле = «не менять»
    try {
      await api('/api/notify/config', { method: 'PUT', body });
      toast('Настройки почты сохранены', 'ok');
      again();
    } catch (e) { toast(e.message, 'err'); }
  };
  const testMail = async () => {
    const to = $('#ne-test-to', host).value.trim();
    if (!to) return toast('Укажите адрес получателя', 'warn');
    try {
      const r = await api('/api/notify/email/test', { method: 'POST', body: { to }, timeout: 300000 });
      toast(`Письмо отправлено (${r.message_id || 'без Message-ID'})`, 'ok');
    } catch (e) { toast(e.message, 'err'); }
  };
  const saveTpl = async () => {
    try {
      await api(`/api/notify/templates/${notifyDomain}`, { method: 'PUT', body: { text: $('#np-text', host).value } });
      toast('Шаблон сохранён', 'ok');
      again();
    } catch (e) { toast(e.message, 'err'); }
  };
  const previewTpl = async () => {
    try {
      const r = await api(`/api/notify/templates/${notifyDomain}/preview`,
        { method: 'POST', body: { text: $('#np-text', host).value } });
      openModal({ title: 'Предпросмотр сообщения', subtitle: (tpls.find(t => t.domain === notifyDomain) || {}).title || '',
        body: html`<pre style="white-space:pre-wrap;font:inherit;margin:0">${r.text}</pre>`,
        footer: html`<button class="btn btn-ghost" data-cancel>Закрыть</button>`,
        onMount(m) { m.querySelector('[data-cancel]').onclick = closeModal; } });
    } catch (e) { toast(e.message, 'err'); }
  };
  const resetTpl = () => {
    confirmDialog('Вернуть текст по умолчанию?', 'Сохранённый шаблон раздела будет заменён исходным текстом.',
      async () => {
        try {
          await api(`/api/notify/templates/${notifyDomain}`, { method: 'PUT', body: { text: tpl.default } });
          toast('Шаблон сброшен к варианту по умолчанию', 'ok');
          again();
        } catch (e) { toast(e.message, 'err'); }
      }, 'Вернуть');
  };

  render(html`
    ${settingsHeadView('Чаты и Почта',
      'Общие настройки доставки для всего приложения: Telegram и почта (MS Exchange), каталог чатов, '
      + 'шаблоны сообщений по разделам. Транспорт один — разделы подключаются к нему со своими получателями.',
      html`<span class=${`badge ${ready.telegram ? 'ok' : 'muted'}`}>Telegram ${ready.telegram ? 'настроен' : 'не настроен'}</span>
       <span class=${`badge ${ready.email ? 'ok' : 'muted'}`}>Почта ${ready.email ? 'настроена' : 'не настроена'}</span>`)}

    ${settingsPanelView('Кто использует доставку', html`
      <div class="table-wrap"><table class="data"><thead><tr>
        <th>Раздел</th><th>Что отправляет</th><th>Получатели</th><th>Статус</th></tr></thead>
        <tbody>${NOTIFY_CONSUMERS.map(c => html`<tr><td><b>${c.area}</b></td><td>${c.what}</td>
          <td>${c.to}</td>
          <td>${c.on ? html`<span class="badge ok">работает</span>` : html`<span class="badge muted">запланировано</span>`}</td></tr>`)}
        </tbody></table></div>
      <p class="hint">Учётные данные и транспорт общие, поэтому новый раздел подключается к доставке,
      не заводя своих токенов: нужны только шаблон сообщения и правило выбора получателей.
      Журнал отправок тоже общий — в нём видно раздел, получателя, канал и статус.</p>`)}

    ${settingsPanelView('Telegram', html`
      <div class="grid-2">
        <label class="field"><span>Токен бота (BotFather)</span>
          <input type="password" id="nt-token" autocomplete="off" placeholder=${tg.token_masked || 'не задан'}>
          ${unreadable.has('notify_telegram_token') ? reenter
            : html`<small class="hint">${tg.token_set ? 'токен сохранён (в поле — маска); заполните, чтобы заменить' : 'токен не задан'}</small>`}</label>
        <label class="field"><span>Адрес Bot API</span>
          <input type="text" id="nt-api" .value=${tg.api || ''} placeholder="https://api.telegram.org">
          <small class="hint">меняют при выходе в интернет через корпоративный прокси</small></label>
      </div>
      <div class="row-actions">
        <button class="btn btn-sm btn-primary" id="nt-save" @click=${saveTelegram}>Сохранить</button>
        <button class="btn btn-sm" id="nt-check" @click=${checkBot}>Проверить бота (getMe)</button>
        <span class="hint" style="margin:0" id="nt-result"></span></div>
      <p class="hint">Токен не показывается и не пишется в журнал аудита — только факт изменения.
      Бота нужно добавить в группы служб: чаты появятся в каталоге ниже, а закрепляются они
      в карточке службы (Ночной отчёт → Справочник → Службы).</p>`)}

    ${settingsPanelView('Каталог чатов Telegram', html`
      <div class="row-actions" style="margin-bottom:8px">
        <button class="btn btn-sm" id="nt-chats" @click=${refreshChats}>Обновить список чатов (getUpdates)</button>
        <span class="hint" style="margin:0">найдено чатов: ${chats.length}</span></div>
      <div class="table-wrap"><table class="data"><thead><tr>
        <th>Название</th><th>chat_id</th><th>Тип</th><th>Виден</th><th>Закреплён за службами</th><th></th></tr></thead>
        <tbody>${chats.length ? chats.map(c => html`<tr>
          <td>${c.title}${c.username ? html` <small class="muted">@${c.username}</small>` : nothing}</td>
          <td><code>${String(c.chat_id)}</code></td>
          <td>${c.kind}</td>
          <td>${c.last_seen ? dateRu(c.last_seen) : '—'}</td>
          <td>${c.used_by.length ? c.used_by.join(', ') : html`<span class="muted">—</span>`}</td>
          <td class="num"><button class="btn btn-sm btn-ghost" data-tg-test=${c.chat_id} @click=${() => testChat(c)}>тест</button></td></tr>`)
          : html`<tr><td colspan="6"><div class="empty">Чатов пока нет: добавьте бота в группу и напишите в ней сообщение, затем обновите список</div></td></tr>`}</tbody></table></div>
      <p class="hint">Обновления не подтверждаются offset: приложение не обрабатывает команды бота,
      а каталог собирается из последних обновлений (Telegram хранит их сутки).</p>`)}

    ${settingsPanelView('Почта (MS Exchange)', html`
      <div class="grid-2">
        <label class="field"><span>Сервер SMTP / коннектор</span>
          <input type="text" id="ne-host" .value=${em.host || ''} placeholder="smtp.resort.local"></label>
        <label class="field"><span>Порт</span>
          <input type="number" id="ne-port" .value=${String(em.port || 587)} min="1" max="65535"></label>
        <label class="field"><span>Шифрование</span><select id="ne-sec">
          ${['none', 'starttls', 'ssl'].map(v => html`<option value=${v} ?selected=${em.security === v}>${
            v === 'none' ? 'без шифрования (релей)' : v === 'starttls' ? 'STARTTLS (587)' : 'SSL (465)'}</option>`)}
        </select></label>
        <label class="field"><span>Адрес отправителя</span>
          <input type="text" id="ne-from" .value=${em.from || ''} placeholder="butler-service@resort.local">
          <small class="hint">должен быть разрешён коннектором Exchange</small></label>
        <label class="field"><span>Пользователь (SMTP AUTH)</span>
          <input type="text" id="ne-user" .value=${em.user || ''} placeholder="пусто — релей без авторизации"></label>
        <label class="field"><span>Пароль</span>
          <input type="password" id="ne-pass" autocomplete="off" placeholder=${em.password_masked || 'не задан'}>
          ${unreadable.has('notify_smtp_password') ? reenter : nothing}</label>
        <label class="field"><span>Адрес для ответа</span>
          <input type="text" id="ne-reply" .value=${em.reply_to || ''} placeholder="необязательно"></label>
        <label class="field"><span>Таймаут, секунд</span>
          <input type="number" id="ne-timeout" .value=${String(cfg.timeout || 20)} min="1" max="300"></label>
      </div>
      <div class="row-actions">
        <button class="btn btn-sm btn-primary" id="ne-save" @click=${saveMail}>Сохранить</button>
        <input type="text" id="ne-test-to" placeholder="кому отправить тестовое письмо" style="max-width:280px">
        <button class="btn btn-sm" id="ne-test" @click=${testMail}>Отправить тестовое письмо</button></div>
      <p class="hint">Поддерживаются оба варианта подключения к Exchange: релей без авторизации
      (пользователь и пароль пустые) и SMTP AUTH. Graph/EWS добавим позже — экран и транспорт
      останутся теми же.</p>`)}

    ${settingsPanelView('Шаблоны сообщений — по разделам', html`
      <label class="field"><span>Раздел</span><select id="np-domain" @change=${e => { notifyDomain = e.target.value; again(); }}>
        ${tpls.map(t => html`<option value=${t.domain} ?selected=${t.domain === tpl.domain}>${t.title}</option>`)}
      </select></label>
      <label class="field"><span>Текст (общий для чата и письма)</span>
        <textarea id="np-text" rows="8" .value=${tpl.text || ''}></textarea></label>
      <p class="hint">Плейсхолдеры (клик — вставить):
        ${(tpl.placeholders || []).map(ph => html`<button class="btn btn-sm btn-ghost" data-ph=${ph}
          @click=${() => { const ta = $('#np-text', host); ta.value += ph; ta.focus(); }}>${ph}</button> `)}</p>
      <div class="row-actions">
        <button class="btn btn-sm btn-primary" id="np-save" @click=${saveTpl}>Сохранить шаблон</button>
        <button class="btn btn-sm" id="np-preview" @click=${previewTpl}>Предпросмотр</button>
        ${tpl.customized ? html`<button class="btn btn-sm btn-ghost" id="np-reset" @click=${resetTpl}>Вернуть текст по умолчанию</button>` : nothing}</div>`)}

    ${settingsPanelView('Медиа и хранение', html`
      <p class="hint" style="margin-top:0">Размер и срок хранения фото и видео задаются в правилах объекта
      (экран «Расчёт» → прочие правила: photo_max_mb, video_max_mb, photo_retention_days,
      video_retention_days). Видео ограничено 50 МБ — это предел загрузки файла в Telegram Bot API.</p>
      <div class="row-actions"><button class="btn btn-sm" id="nt-rules" @click=${() => settingsGo('calc')}>Открыть правила объекта</button></div>`)}

    ${settingsPanelView('Журнал отправок', html`
      <p class="hint" style="margin-top:0">Журнал общий для всех разделов: раздел, получатель, канал,
      состав отправки снимком, статус, ошибка и число попыток. Неудачную доставку можно повторить
      из раздела-владельца (например, из экрана «Недостатки смены»).</p>
      <div class="row-actions"><button class="btn btn-sm" id="nt-csv" @click=${() => downloadBlob('/api/notify/dispatches/export.csv', 'otpravki.csv')}>Выгрузить журнал (CSV)</button></div>`)}
  `, mount(host));
}
