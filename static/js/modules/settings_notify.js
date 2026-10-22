/* Раздел «Настройки»: экран «Чаты и Почта» (вынесено из settings.js, шаг 6.5 аудита).
   Оболочка, черновик версии справочников и общие помощники — в settings.js. */
'use strict';

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
let NOTIFY_DOMAIN = 'night';

async function settingsScreenNotify(host) {
  let data;
  try { data = await api('/api/notify/config'); }
  catch (e) {
    host.innerHTML = settingsHead('Чаты и Почта', '') + `<div class="empty">${esc(e.message)}</div>`;
    return;
  }
  const cfg = data.config || {};
  const tg = cfg.telegram || {}, em = cfg.email || {}, ready = cfg.ready || {};
  const chats = data.chats || [];
  let tpls = [];
  try { tpls = (await api('/api/notify/templates')).templates || []; } catch { tpls = []; }
  if (!tpls.some(t => t.domain === NOTIFY_DOMAIN)) NOTIFY_DOMAIN = (tpls[0] || {}).domain || 'night';
  const tpl = tpls.find(t => t.domain === NOTIFY_DOMAIN) || { text: '', placeholders: [] };

  host.innerHTML = `
    ${settingsHead('Чаты и Почта',
      'Общие настройки доставки для всего приложения: Telegram и почта (MS Exchange), каталог чатов, '
      + 'шаблоны сообщений по разделам. Транспорт один — разделы подключаются к нему со своими получателями.',
      `<span class="badge ${ready.telegram ? 'ok' : 'muted'}">Telegram ${ready.telegram ? 'настроен' : 'не настроен'}</span>
       <span class="badge ${ready.email ? 'ok' : 'muted'}">Почта ${ready.email ? 'настроена' : 'не настроена'}</span>`)}

    ${settingsPanel('Кто использует доставку', `
      <div class="table-wrap"><table class="data"><thead><tr>
        <th>Раздел</th><th>Что отправляет</th><th>Получатели</th><th>Статус</th></tr></thead>
        <tbody>${NOTIFY_CONSUMERS.map(c => `<tr><td><b>${esc(c.area)}</b></td><td>${esc(c.what)}</td>
          <td>${esc(c.to)}</td>
          <td>${c.on ? '<span class="badge ok">работает</span>' : '<span class="badge muted">запланировано</span>'}</td></tr>`).join('')}
        </tbody></table></div>
      <p class="hint">Учётные данные и транспорт общие, поэтому новый раздел подключается к доставке,
      не заводя своих токенов: нужны только шаблон сообщения и правило выбора получателей.
      Журнал отправок тоже общий — в нём видно раздел, получателя, канал и статус.</p>`)}

    ${settingsPanel('Telegram', `
      <div class="grid-2">
        <label class="field"><span>Токен бота (BotFather)</span>
          <input type="password" id="nt-token" autocomplete="off" placeholder="${esc(tg.token_masked || 'не задан')}">
          <small class="hint">${tg.token_set ? 'токен сохранён (в поле — маска); заполните, чтобы заменить' : 'токен не задан'}</small></label>
        <label class="field"><span>Адрес Bot API</span>
          <input type="text" id="nt-api" value="${esc(tg.api || '')}" placeholder="https://api.telegram.org">
          <small class="hint">меняют при выходе в интернет через корпоративный прокси</small></label>
      </div>
      <div class="row-actions">
        <button class="btn btn-sm btn-primary" id="nt-save">Сохранить</button>
        <button class="btn btn-sm" id="nt-check">Проверить бота (getMe)</button>
        <span class="hint" style="margin:0" id="nt-result"></span></div>
      <p class="hint">Токен не показывается и не пишется в журнал аудита — только факт изменения.
      Бота нужно добавить в группы служб: чаты появятся в каталоге ниже, а закрепляются они
      в карточке службы (Ночной отчёт → Справочник → Службы).</p>`, '')}

    ${settingsPanel('Каталог чатов Telegram', `
      <div class="row-actions" style="margin-bottom:8px">
        <button class="btn btn-sm" id="nt-chats">Обновить список чатов (getUpdates)</button>
        <span class="hint" style="margin:0">найдено чатов: ${chats.length}</span></div>
      <div class="table-wrap"><table class="data"><thead><tr>
        <th>Название</th><th>chat_id</th><th>Тип</th><th>Виден</th><th>Закреплён за службами</th><th></th></tr></thead>
        <tbody>${chats.map(c => `<tr>
          <td>${esc(c.title)}${c.username ? ` <small class="muted">@${esc(c.username)}</small>` : ''}</td>
          <td><code>${esc(String(c.chat_id))}</code></td>
          <td>${esc(c.kind)}</td>
          <td>${esc(c.last_seen ? dateRu(c.last_seen) : '—')}</td>
          <td>${c.used_by.length ? c.used_by.map(esc).join(', ') : '<span class="muted">—</span>'}</td>
          <td class="num"><button class="btn btn-sm btn-ghost" data-tg-test="${c.chat_id}">тест</button></td></tr>`).join('')
          || '<tr><td colspan="6"><div class="empty">Чатов пока нет: добавьте бота в группу и напишите в ней сообщение, затем обновите список</div></td></tr>'}</tbody></table></div>
      <p class="hint">Обновления не подтверждаются offset: приложение не обрабатывает команды бота,
      а каталог собирается из последних обновлений (Telegram хранит их сутки).</p>`)}

    ${settingsPanel('Почта (MS Exchange)', `
      <div class="grid-2">
        <label class="field"><span>Сервер SMTP / коннектор</span>
          <input type="text" id="ne-host" value="${esc(em.host || '')}" placeholder="smtp.resort.local"></label>
        <label class="field"><span>Порт</span>
          <input type="number" id="ne-port" value="${em.port || 587}" min="1" max="65535"></label>
        <label class="field"><span>Шифрование</span><select id="ne-sec">
          ${['none', 'starttls', 'ssl'].map(v => `<option value="${v}" ${em.security === v ? 'selected' : ''}>${
            v === 'none' ? 'без шифрования (релей)' : v === 'starttls' ? 'STARTTLS (587)' : 'SSL (465)'}</option>`).join('')}
        </select></label>
        <label class="field"><span>Адрес отправителя</span>
          <input type="text" id="ne-from" value="${esc(em.from || '')}" placeholder="butler-service@resort.local">
          <small class="hint">должен быть разрешён коннектором Exchange</small></label>
        <label class="field"><span>Пользователь (SMTP AUTH)</span>
          <input type="text" id="ne-user" value="${esc(em.user || '')}" placeholder="пусто — релей без авторизации"></label>
        <label class="field"><span>Пароль</span>
          <input type="password" id="ne-pass" autocomplete="off" placeholder="${esc(em.password_masked || 'не задан')}"></label>
        <label class="field"><span>Адрес для ответа</span>
          <input type="text" id="ne-reply" value="${esc(em.reply_to || '')}" placeholder="необязательно"></label>
        <label class="field"><span>Таймаут, секунд</span>
          <input type="number" id="ne-timeout" value="${cfg.timeout || 20}" min="1" max="300"></label>
      </div>
      <div class="row-actions">
        <button class="btn btn-sm btn-primary" id="ne-save">Сохранить</button>
        <input type="text" id="ne-test-to" placeholder="кому отправить тестовое письмо" style="max-width:280px">
        <button class="btn btn-sm" id="ne-test">Отправить тестовое письмо</button></div>
      <p class="hint">Поддерживаются оба варианта подключения к Exchange: релей без авторизации
      (пользователь и пароль пустые) и SMTP AUTH. Graph/EWS добавим позже — экран и транспорт
      останутся теми же.</p>`)}

    ${settingsPanel('Шаблоны сообщений — по разделам', `
      <label class="field"><span>Раздел</span><select id="np-domain">
        ${tpls.map(t => `<option value="${esc(t.domain)}" ${t.domain === tpl.domain ? 'selected' : ''}>${esc(t.title)}</option>`).join('')}
      </select></label>
      <label class="field"><span>Текст (общий для чата и письма)</span>
        <textarea id="np-text" rows="8">${esc(tpl.text || '')}</textarea></label>
      <p class="hint">Плейсхолдеры (клик — вставить):
        ${(tpl.placeholders || []).map(ph => `<button class="btn btn-sm btn-ghost" data-ph="${esc(ph)}">${esc(ph)}</button>`).join(' ')}</p>
      <div class="row-actions">
        <button class="btn btn-sm btn-primary" id="np-save">Сохранить шаблон</button>
        <button class="btn btn-sm" id="np-preview">Предпросмотр</button>
        ${tpl.customized ? '<button class="btn btn-sm btn-ghost" id="np-reset">Вернуть текст по умолчанию</button>' : ''}</div>`)}

    ${settingsPanel('Медиа и хранение', `
      <p class="hint" style="margin-top:0">Размер и срок хранения фото и видео задаются в правилах объекта
      (экран «Расчёт» → прочие правила: photo_max_mb, video_max_mb, photo_retention_days,
      video_retention_days). Видео ограничено 50 МБ — это предел загрузки файла в Telegram Bot API.</p>
      <div class="row-actions"><button class="btn btn-sm" id="nt-rules">Открыть правила объекта</button></div>`)}

    ${settingsPanel('Журнал отправок', `
      <p class="hint" style="margin-top:0">Журнал общий для всех разделов: раздел, получатель, канал,
      состав отправки снимком, статус, ошибка и число попыток. Неудачную доставку можно повторить
      из раздела-владельца (например, из экрана «Недостатки смены»).</p>
      <div class="row-actions"><button class="btn btn-sm" id="nt-csv">Выгрузить журнал (CSV)</button></div>`)}
  `;

  /* ── Telegram ── */
  settingsOn('#nt-save', host, async () => {
    const body = { notify_telegram_api: $('#nt-api').value.trim() };
    const token = $('#nt-token').value.trim();
    if (token) body.notify_telegram_token = token;      // пустое поле = «не менять»
    try {
      const r = await api('/api/notify/config', { method: 'PUT', body });
      toast(`Настройки Telegram сохранены${r.changed.length ? ` (${r.changed.length})` : ''}`, 'ok');
      settingsScreenNotify(host);
    } catch (e) { toast(e.message, 'err'); }
  });
  settingsOn('#nt-check', host, async () => {
    const out = $('#nt-result');
    out.textContent = 'проверяем…';
    try {
      // таймаут канала в настройках — до 300 с, обычные 20 с клиента обрывали бы проверку (UI-03)
      const r = await api('/api/notify/telegram/check', { method: 'POST', timeout: 300000,
        body: { token: $('#nt-token').value.trim(), api: $('#nt-api').value.trim() } });
      out.textContent = `бот: @${r.bot.username || '—'} (${r.bot.first_name || ''})`;
      toast('Токен принят Telegram', 'ok');
    } catch (e) { out.textContent = ''; toast(e.message, 'err'); }
  });
  settingsOn('#nt-chats', host, async () => {
    try {
      const r = await api('/api/notify/telegram/chats', { method: 'POST' });
      toast(`Каталог обновлён: найдено ${r.seen}, добавлено ${r.added}`, 'ok');
      settingsScreenNotify(host);
    } catch (e) { toast(e.message, 'err'); }
  });
  $$('[data-tg-test]', host).forEach(b => b.onclick = async () => {
    try {
      await api('/api/notify/telegram/test', { method: 'POST', body: { chat_id: Number(b.dataset.tgTest) } });
      toast('Тестовое сообщение отправлено в чат', 'ok');
    } catch (e) { toast(e.message, 'err'); }
  });

  /* ── Почта ── */
  settingsOn('#ne-save', host, async () => {
    const body = {
      notify_smtp_host: $('#ne-host').value.trim(), notify_smtp_port: $('#ne-port').value.trim(),
      notify_smtp_security: $('#ne-sec').value, notify_smtp_user: $('#ne-user').value.trim(),
      notify_email_from: $('#ne-from').value.trim(), notify_email_reply_to: $('#ne-reply').value.trim(),
      notify_timeout: $('#ne-timeout').value.trim(),
    };
    const pass = $('#ne-pass').value;
    if (pass) body.notify_smtp_password = pass;          // пустое поле = «не менять»
    try {
      await api('/api/notify/config', { method: 'PUT', body });
      toast('Настройки почты сохранены', 'ok');
      settingsScreenNotify(host);
    } catch (e) { toast(e.message, 'err'); }
  });
  settingsOn('#ne-test', host, async () => {
    const to = $('#ne-test-to').value.trim();
    if (!to) return toast('Укажите адрес получателя', 'warn');
    try {
      const r = await api('/api/notify/email/test', { method: 'POST', body: { to }, timeout: 300000 });
      toast(`Письмо отправлено (${r.message_id || 'без Message-ID'})`, 'ok');
    } catch (e) { toast(e.message, 'err'); }
  });

  /* ── Шаблоны ── */
  settingsOn('#np-domain', host, () => {
    NOTIFY_DOMAIN = $('#np-domain').value;
    settingsScreenNotify(host);
  });
  $$('[data-ph]', host).forEach(b => b.onclick = () => {
    const ta = $('#np-text');
    ta.value += b.dataset.ph;
    ta.focus();
  });
  settingsOn('#np-save', host, async () => {
    try {
      await api(`/api/notify/templates/${NOTIFY_DOMAIN}`, { method: 'PUT', body: { text: $('#np-text').value } });
      toast('Шаблон сохранён', 'ok');
      settingsScreenNotify(host);
    } catch (e) { toast(e.message, 'err'); }
  });
  settingsOn('#np-preview', host, async () => {
    try {
      const r = await api(`/api/notify/templates/${NOTIFY_DOMAIN}/preview`,
        { method: 'POST', body: { text: $('#np-text').value } });
      openModal({ title: 'Предпросмотр сообщения', subtitle: (tpls.find(t => t.domain === NOTIFY_DOMAIN) || {}).title || '',
        body: `<pre style="white-space:pre-wrap;font:inherit;margin:0">${esc(r.text)}</pre>`,
        footer: '<button class="btn btn-ghost" data-cancel>Закрыть</button>',
        onMount(m) { m.querySelector('[data-cancel]').onclick = closeModal; } });
    } catch (e) { toast(e.message, 'err'); }
  });
  settingsOn('#np-reset', host, () => {
    const t = tpls.find(x => x.domain === NOTIFY_DOMAIN);
    if (!t) return;
    confirmDialog('Вернуть текст по умолчанию?', 'Сохранённый шаблон раздела будет заменён исходным текстом.',
      async () => {
        try {
          await api(`/api/notify/templates/${NOTIFY_DOMAIN}`, { method: 'PUT', body: { text: t.default } });
          toast('Шаблон сброшен к варианту по умолчанию', 'ok');
          settingsScreenNotify(host);
        } catch (e) { toast(e.message, 'err'); }
      }, 'Вернуть');
  });
  settingsOn('#nt-rules', host, () => settingsGo('calc'));
  settingsOn('#nt-csv', host, () => downloadBlob('/api/notify/dispatches/export.csv', 'otpravki.csv'));
}
