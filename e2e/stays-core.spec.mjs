/* «Шахматка», основные виды (шаг 6д-1): объекты, батлеры, табло дня, загрузка, брони. */
import { expect, test } from '@playwright/test';
import { login, watchErrors } from './helpers.mjs';

const open = (page, view) => page.evaluate(v => window.navigate(v), view);
const tab = (page, id) => page.locator(`#view-stays [data-stab=${id}]`);
const openFilters = async view => {
  const toggle = view.locator('.sf-toggle');
  if (await toggle.getAttribute('aria-expanded') === 'false') await toggle.click();
};
const openExports = async view => {
  const menu = view.locator('.sb-exports');
  if (await menu.getAttribute('open') === null) await menu.locator('summary').click();
};
const clickExport = async (view, action, options) => {
  await openExports(view);
  await action.click(options);
};


test('поиск шахматки сохраняет форму при клике и фокусе с клавиатуры', async ({ page }) => {
  await login(page, 'admin');
  await open(page, 'stays');
  const search = page.locator('#sf-q');
  await expect(search).toBeVisible();
  const appearance = () => search.evaluate(input => {
    const style = getComputedStyle(input);
    const { width, height } = input.getBoundingClientRect();
    return { width, height, padding: style.padding, radius: style.borderRadius, icon: style.backgroundImage };
  });
  const idle = await appearance();
  await search.click();
  expect(await appearance()).toEqual(idle);
  expect(idle.icon).not.toBe('none');
  await expect(search).toHaveCSS('outline-style', 'solid');
  await expect(search).toHaveCSS('box-shadow', 'none');

  await page.keyboard.press('Shift+Tab');
  await expect(search).not.toBeFocused();
  await page.keyboard.press('Tab');
  await expect(search).toBeFocused();
  expect(await appearance()).toEqual(idle);
  await expect(search).toHaveCSS('outline-style', 'solid');
  await expect(search).toHaveCSS('box-shadow', 'none');
});

test.describe('печать шахматки', () => {
  test.use({ serviceWorkers: 'block' });
  test.beforeEach(async ({ page }) => {
    await page.route('**/api/stays/board/units/export?**', route =>
      route.fulfill({ status: 502, json: { detail: 'Тест резервной печати' } }));
  });
  for (const transition of ['выход', 'истечение сессии', '401 при печати', 'вход как сотрудник']) {
    test(`закрывает печать при смене сессии · ${transition}`, async ({ page }) => {
      await page.addInitScript(() => { window.print = () => {}; });
      await login(page, 'admin');
      await open(page, 'stays');
      const action = page.locator('#sb-print');
      await expect(action).toBeEnabled();
      // Пустой ответ без автопечати. Второй документ ждёт освобождения тела ответа.
      await page.evaluate(rejectThird => {
        const fetch = window.fetch.bind(window);
        let prints = 0;
        window.fetch = (...args) => {
          if (args[0] !== '/api/docs/print') return fetch(...args);
          if (++prints === 3 && rejectThird) return Promise.resolve(new Response(null, { status: 401 }));
          const wait = prints === 2;
          const context = document.cookie.match(/(?:^|;\s*)tt_auth_context=([^;]+)/)?.[1];
          return Promise.resolve({ ok: true, status: 200,
            headers: new Headers({ 'X-Butler-Auth-Context': decodeURIComponent(context) }), text: async () => {
            if (wait) await new Promise(resolve => { window.releasePrint = resolve; });
            return '<p>Тест печати</p>';
          } });
        };
      }, transition === '401 при печати');
      await clickExport(page.locator('#view-stays'), action);
      const frames = page.locator('body > iframe[srcdoc]');
      await expect(frames).toHaveCount(1);
      await clickExport(page.locator('#view-stays'), action);
      await page.waitForFunction(() => !!window.releasePrint);
      if (transition === 'вход как сотрудник') {
        await open(page, 'employees');
        await page.locator('#view-employees [data-card]').filter({ hasText: 'Иванов' }).first().click();
        await page.locator('#modal [data-imp]').click();
        await expect(page.locator('#impersonation-bar')).toBeVisible();
      } else {
        if (transition === 'выход') {
          await page.locator('#logout-btn').click();
        } else if (transition === '401 при печати') {
          const reloaded = page.waitForEvent('domcontentloaded');
          await clickExport(page.locator('#view-stays'), action);
          await reloaded;
          await expect(page.locator('#user-name')).toContainText('admin');
        } else {
          await page.route('**/api/auth/me', route => route.fulfill({ status: 401, json: {} }));
          await page.route('**/api/auth/context', route => route.fulfill({ status: 401, json: {} }));
          await page.evaluate(async () => {
            const { api } = await import('/static/js/core.js');
            await api('/api/auth/me', { silent: true }).catch(() => {});
          });
        }
        if (transition !== '401 при печати') await expect(page.locator('#login-screen')).toBeVisible();
      }
      await expect(frames, 'открытый документ закрыт').toHaveCount(0);
      await page.evaluate(() => window.releasePrint?.());
      await expect(frames, 'задержанный документ не появился').toHaveCount(0);
      if (transition === 'вход как сотрудник') {
        await page.evaluate(async () => {
          const { printWindow } = await import('/static/js/modules/docs.js');
          await printWindow('Документ сотрудника', '<p>Тест</p>');
        });
        await expect(frames).toHaveCount(1);
        await page.locator('#stop-impersonation').click();
        await expect(page.locator('#impersonation-bar')).toBeHidden();
        await expect(frames).toHaveCount(0);
      }
    });
  }

  test('объединяет поиск и категорию до отправки фильтров', async ({ page }) => {
    await login(page, 'admin');
    await page.addInitScript(() => { window.print = () => {}; });
    await open(page, 'stays');
    const view = page.locator('#view-stays');
    const action = view.locator('#sb-print');
    await expect(action).toBeEnabled();
    await openFilters(view);
    await view.locator('[data-sf-dd=cat] summary').click();
    const box = view.locator('[data-sf-cat]').first();
    const category = await box.getAttribute('data-sf-cat');
    const code = (await box.locator('..').innerText()).trim();
    const criteria = [];
    await page.route('**/api/stays/board/units?**', async route => {
      const params = new URL(route.request().url()).searchParams;
      const pair = [params.get('q'), params.get('category_ids')];
      criteria.push(pair);
      const response = await route.fetch();
      const data = await response.json();
      data.units[0].label = pair[0] === 'Орлов' && pair[1] === category ? 'Оба критерия' : 'Неполный выбор';
      await route.fulfill({ response, json: data });
    });
    await page.clock.install();
    await view.locator('#sf-q').fill('Орлов');
    await box.check();
    await page.clock.runFor(450);
    await expect(action).toBeEnabled();
    await clickExport(page.locator('#view-stays'), action);
    const print = page.frameLocator('iframe[srcdoc]');
    await expect(print.locator('h1')).toBeAttached();
    const summary = await print.locator('p').first().textContent();
    expect.soft(summary).toContain('Поиск: Орлов');
    expect.soft(summary).toContain('Категории: ' + code);
    expect.soft(await print.locator('tbody th').filter({ hasText: 'Оба критерия' }).count()).toBeGreaterThan(0);
    expect(criteria).toEqual([['Орлов', category]]);
  });

  test('сброс отменяет поиск из прежней панели', async ({ page }) => {
    await login(page, 'admin');
    await open(page, 'stays');
    const view = page.locator('#view-stays');
    const search = view.locator('#sf-q');
    await expect(search).toBeVisible();
    const queries = [];
    page.on('request', req => {
      if (req.url().includes('/api/stays/board/units?')) queries.push(new URL(req.url()).searchParams.get('q'));
    });
    await openFilters(view);
    const controlTime = new Date();
    await page.clock.install({ time: controlTime });
    await page.clock.pauseAt(new Date(controlTime.getTime() + 1000));
    for (const redraw of [true, false]) {
      queries.length = 0;
      await search.fill('Орлов');
      if (redraw) await view.locator('#sb-sort').selectOption('label');
      await view.locator('#sf-reset').click();
      await page.clock.runFor(450);
      await expect(view.locator('#sb-print')).toBeEnabled();
      expect(await search.inputValue()).toBe('');
      await expect(view.locator('#sf-reset')).toBeHidden();
      expect(queries).toEqual([null]);
    }
  });

  test('запоздавшая шахматка не возвращает печать поверх новой вкладки', async ({ page }) => {
    await login(page, 'admin');
    await open(page, 'stays');
    const view = page.locator('#view-stays');
    await expect(view.locator('#sb-print')).toBeEnabled();

    let releaseBoard, markBoardStarted;
    const boardGate = new Promise(resolve => { releaseBoard = resolve; });
    const boardStarted = new Promise(resolve => { markBoardStarted = resolve; });
    await page.route('**/api/stays/board/units?**', async route => {
      markBoardStarted();
      await boardGate;
      await route.continue();
    });

    let releaseFund, markFundsStarted;
    const fundGate = new Promise(resolve => { releaseFund = resolve; });
    const fundsStarted = new Promise(resolve => { markFundsStarted = resolve; });
    let fundRequests = 0;
    const holdFund = async route => {
      if (++fundRequests === 2) markFundsStarted();
      await fundGate;
      await route.continue();
    };
    await page.route('**/api/stays/fund', holdFund);
    await page.route('**/api/stays/fund/snapshot?**', holdFund);

    try {
      await view.locator('#sm-next').click();
      await boardStarted;
      await tab(page, 'day').click();
      await fundsStarted;
      const oldResponse = page.waitForResponse(r => r.url().includes('/api/stays/board/units?'));
      releaseBoard();
      await oldResponse;
      await page.waitForTimeout(200); // дать старому async-render дойти до возможного commit
      await expect(view.locator('[data-stab][aria-pressed=true]')).toHaveText('Табло дня');
      await expect(view.locator('#sb-print')).toHaveCount(0);
    } finally {
      releaseBoard();
      releaseFund();
    }
  });

  test('показывает код категории за выбранный прошлый месяц', async ({ page }) => {
    await login(page, 'admin');
    await page.addInitScript(() => { window.print = () => {}; });
    await open(page, 'stays');
    const view = page.locator('#view-stays');
    await expect(view.locator('#sb-print')).toBeEnabled();
    let expected;
    await page.route('**/api/stays/board/units?**', async route => {
      const response = await route.fetch();
      const data = await response.json();
      const unit = data.units[0];
      unit.category = 'OLD';
      unit.categories = [{ from: data.days[0], category_id: unit.category_id, code: 'OLD' },
        { from: data.days[14], category_id: unit.category_id, code: 'NEW' }];
      expected = 'OLD → NEW с 15.' + data.days[14].slice(5, 7);
      await route.fulfill({ response, json: data });
    });
    await view.locator('#sm-prev').click();
    await expect(view.locator('#sb-print')).toBeEnabled();
    await openFilters(view);
    await view.locator('#sb-grouped').uncheck();
    expect.soft(await view.locator('.sb-change').allTextContents()).toContain(expected);
    await clickExport(view, view.locator('#sb-print'));
    const table = page.frameLocator('iframe[srcdoc]').locator('table');
    await expect(table).toBeAttached();
    expect(await table.textContent()).toContain(expected);
  });

  test('ждёт выбранный фильтр перед печатью', async ({ page }) => {
    await login(page, 'admin');
    await page.addInitScript(() => { window.print = () => {}; });
    await open(page, 'stays');
    const view = page.locator('#view-stays');
    const action = view.locator('#sb-print');
    await expect(action).toBeEnabled();
    const prints = [];
    page.on('request', req => { if (req.url().endsWith('/api/docs/print')) prints.push(req); });
    let release;
    const pending = new Promise(resolve => { release = resolve; });
    await page.route('**/api/stays/board/units?**', async route => {
      await pending;
      await route.continue();
    });
    const search = view.locator('#sf-q');
    const isSearch = req => req.url().includes('/api/stays/board/units?')
      && new URL(req.url()).searchParams.get('q') === 'Орлов';
    const requested = page.waitForRequest(isSearch);
    const response = page.waitForResponse(isSearch);
    try {
      await search.fill('Орлов');
      expect.soft(await action.isDisabled(), 'пока ввод ожидает отправки').toBe(true);
      await requested;
      await clickExport(view, action, { force: true });
      expect.soft(await action.isDisabled(), 'пока запрос не завершён').toBe(true);
      // Локальная сортировка также не должна активировать устаревший ответ.
      await openFilters(view);
      await view.locator('#sb-sort').selectOption('label');
      expect.soft(await action.isDisabled()).toBe(true);
    } finally {
      release();
    }
    await response;
    await expect(action).toBeEnabled();
    await clickExport(page.locator('#view-stays'), action);
    const frames = page.locator('iframe[srcdoc]');
    await expect(frames.last().contentFrame().locator('p').first()).toContainText('Поиск: Орлов');
    expect(prints).toHaveLength(1);
  });

  test('печатает смены обозначения и категории с датами доски', async ({ page }) => {
    await login(page, 'admin');
    await page.addInitScript(() => { window.print = () => {}; });
    const cats = await page.evaluate(async () => {
      const { staysFund } = await import('/static/js/modules/stays.js');
      return (await staysFund()).categories.slice(0, 2);
    });
    let mm;
    await page.route('**/api/stays/board/units?**', async route => {
      const response = await route.fetch();
      const data = await response.json();
      mm = data.days[0].slice(5, 7);
      const unit = data.units[0];
      Object.assign(unit, { label: 'Дом 7', category: cats[0].code, category_id: cats[0].id,
        labels: [{ from: data.days[0], label: 'Дом 7' }, { from: data.days[10], label: 'Дом <17>' }],
        categories: [{ from: data.days[0], category_id: cats[0].id },
          { from: data.days[18], category_id: cats[1].id }] });
      await route.fulfill({ response, json: data });
    });
    await open(page, 'stays');
    const view = page.locator('#view-stays');
    await openFilters(view);
    await view.locator('#sb-grouped').uncheck();
    const rename = `Дом 7 → Дом <17> с 11.${mm}`;
    const reclassify = `${cats[0].code} → ${cats[1].code} с 19.${mm}`;
    const screen = view.locator('.sb-change').filter({ hasText: rename });
    await expect(screen).toContainText(reclassify);
    await clickExport(view, view.locator('#sb-print'));
    const caption = page.frameLocator('iframe[srcdoc]').locator('tbody th').filter({ hasText: 'Дом 7' }).first();
    await expect(caption).toBeVisible();
    const printed = await caption.textContent();
    expect.soft(printed).toContain(rename);
    expect.soft(printed).toContain(reclassify);
  });

  test('печатает все критерии сохранённого набора без данных гостей', async ({ page }) => {
    await login(page, 'sluzhba');
    await page.addInitScript(() => { window.print = () => {}; });
    const category = await page.evaluate(async () => {
      const { staysFund, staysState } = await import('/static/js/modules/stays.js');
      const { staysSaveFilter } = await import('/static/js/modules/stays_filters.js');
      const cat = (await staysFund()).categories[0];
      staysSaveFilter('Прежний фонд', { category_ids: [cat.id, 8012345], kind_ids: [8012346, 8012347] });
      Object.assign(staysState.filters, { q: 'скрытая фамилия', special: true, vip_code_ids: [8012348] });
      return cat.code;
    });
    await open(page, 'stays');
    const view = page.locator('#view-stays');
    await openFilters(view);
    await view.locator('#sf-saved').selectOption('Прежний фонд');
    await expect(view.locator('.chip', { hasText: '8012347' })).toBeVisible();
    await clickExport(view, view.locator('#sb-print'));
    const frame = page.frameLocator('iframe[srcdoc]');
    const filters = frame.locator('p').first();
    await expect(filters).toContainText(category);
    const printed = await filters.textContent();
    for (const id of ['8012345', '8012346', '8012347']) expect.soft(printed).toContain(id);
    expect(await frame.locator('html').evaluate(el => el.outerHTML)).not.toMatch(/8012348|VIP|◆|скрытая фамилия/i);
  });
  for (const [loginName, level] of [['admin', 'full'], ['ivanov', 'names'], ['sluzhba', 'occupancy']]) {
    test(level, async ({ page }) => {
      await login(page, loginName);
      // Headless Chromium может мгновенно закрыть диалог. Управляем только его закрытием.
      await page.addInitScript(() => { window.print = () => { window.printInvoked = true; }; });
      let category;
      await page.route('**/api/stays/board/units?**', async route => {
        const response = await route.fetch();
        const data = await response.json();
        expect(data.visibility).toBe(level);
        category = data.units[0].category_id;
        const filtered = new URL(route.request().url()).searchParams.has('category_ids');
        data.units[0].label = filtered ? 'Вилла на склоне' : 'Из нефильтрованной доски';
        const start = data.days[2], end = data.days[4];
        const pos = iso => (Date.parse(iso) / 86400000 + 719163) * 2;
        // Лишние поля даже у младших ролей: печать сама выбирает разрешённые данные.
        data.bars = [{ unit_id: data.units[0].unit_id, start, end, start_pos: pos(start) + 1,
          end_pos: pos(end), status: 'confirmed', guests_count: 7, reservation_id: 981234567,
          main_guest: 'Гость <Тест>', number: 'RES-PRINT-78', vip_code: 'VIP-PRINT', special: true,
          customer: 'Заказчик-Свидетель', note: 'Закрытая заметка' }];
        data.bars.push({ ...data.bars[0], unit_id: null, guests_count: 2 });
        data.holds = [{ ...data.bars[0], kind: 'ooo', title: 'Замена окон' }];
        data.blocks = [{ ...data.bars[0], title: 'Конгресс' }];
        await route.fulfill({ response, json: data });
      });
      await page.evaluate(async () => {
        const { staysState } = await import('/static/js/modules/stays.js');
        Object.assign(staysState.filters, { q: 'частный поиск', special: true, vip_code_ids: [1] });
      });
      await open(page, 'stays');
      const view = page.locator('#view-stays');
      await expect(view.locator('.sb-grid')).toBeVisible();
      const action = view.locator('#sb-print');
      await openExports(view);
      await expect(action).toBeVisible();
      expect(await action.evaluate(el => el.previousElementSibling.id)).toBe('sb-board-pdf');
      const label = view.locator('#sm-label');
      const previous = (await label.textContent()).trim();
      await view.locator('#sm-next').click();
      await expect(label).not.toHaveText(previous);
      const month = (await label.textContent()).trim();
      await openFilters(view);
      await view.locator('[data-sf-dd=cat] summary').click();
      const box = view.locator(`[data-sf-cat="${category}"]`);
      const code = (await box.locator('..').innerText()).trim();
      await box.check();
      await expect(view.locator('[data-sf-dd=cat] summary b')).toHaveText(code);
      const reads = [];
      page.on('request', req => { if (req.url().includes('/api/stays/')) reads.push(req.url()); });
      await page.evaluate(() => {
        window.addEventListener('message', ({ source, data, origin }) => {
          if (data?.butler_print_done !== true) return;
          const frame = document.querySelector('iframe[srcdoc]');
          window.printDone = !!frame && source === frame.contentWindow && origin === location.origin;
        });
      });
      await clickExport(page.locator('#view-stays'), action);
      const frame = page.frameLocator('iframe[aria-hidden=true][srcdoc]');
      await expect(frame.locator('h1')).toContainText(month);
      await expect(frame.locator('p', { hasText: 'Категории' })).toContainText(code);
      await expect(frame.locator('table')).toContainText('Вилла на склоне');
      const booking = frame.getByRole('row').filter({ hasText: '7 гост.' });
      await expect(booking).toContainText('Вилла на склоне');
      await expect(booking.locator('td').nth(3)).toHaveText('◑');
      await expect(booking.locator('td').nth(4)).toHaveText('●');
      await expect(booking.locator('td').nth(5)).toHaveText('◐');
      await expect(frame.locator('table')).toContainText('Не распределено');
      await expect(frame.locator('table')).toContainText('2 гост.');
      await expect(frame.locator('table')).toContainText('OOO');
      await expect(frame.locator('table')).toContainText('Блок');
      const dayCount = await view.locator('.sb-head [data-day]').count();
      await expect(frame.locator('thead th').last()).toHaveText(String(dayCount));
      const markup = await frame.locator('html').evaluate(el => el.outerHTML);
      expect(markup).not.toMatch(/981234567|Из нефильтрованной доски/);
      if (level === 'occupancy') {
        expect(markup).not.toMatch(/Гость &lt;Тест|RES-PRINT|VIP|◆|особый гость|частный поиск|Конгресс|Замена окон/i);
      } else {
        await expect(frame.locator('p', { hasText: 'Категории' })).toContainText('частный поиск');
        await expect(frame.locator('table')).toContainText('Гость <Тест>');
        expect(markup).toContain('RES-PRINT-78');
        expect(markup).toContain('VIP-PRINT');
        expect(markup).toContain('◆');
      }
      for (const field of ['Заказчик-Свидетель', 'Закрытая заметка']) {
        expect(markup.includes(field)).toBe(level === 'full');
      }
      await expect.poll(() => frame.locator('html').evaluate(() => window.printInvoked)).toBe(true);
      await frame.locator('html').evaluate(() => window.dispatchEvent(new Event('afterprint')));
      await expect(page.locator('iframe[srcdoc]')).toHaveCount(0);
      expect(await page.evaluate(() => window.printDone)).toBe(true);
      expect(reads).toHaveLength(1);
      expect(new URL(reads[0]).pathname).toBe('/api/stays/board/units/export');
      expect(new URL(reads[0]).searchParams.get('format')).toBe('pdf');
    });
  }
});

test('вкладки по правам и шахматка объектов: сетка, разделы дерева, сортировка', async ({ page }) => {
  const errors = watchErrors(page);
  await login(page, 'admin');
  await open(page, 'stays');
  const view = page.locator('#view-stays');
  expect(await view.locator('[data-stab]').count()).toBeGreaterThanOrEqual(6);
  await expect(view.locator('[data-stab][aria-pressed=true]')).toHaveText('Объекты');
  await expect(view.locator('.sb-grid')).toBeVisible();
  await expect(view.locator('#stays-body')).not.toContainText('Загрузка…');
  await openFilters(view);
  await expect(view.locator('.sf-panel')).toBeVisible();
  const rows = await view.locator('[data-unit-row]').count();
  expect(rows).toBeGreaterThan(5);
  expect(await view.locator('.sb-head [data-day]').count()).toBeGreaterThanOrEqual(28);
  expect(await view.locator('.sb-bar').count()).toBeGreaterThan(0);
  // раздел дерева сворачивается и разворачивается
  const sec = view.locator('[data-sec][data-open="1"]').first();
  const name = await sec.locator('span').textContent();
  await sec.click();
  await expect(view.locator('[data-sec]', { hasText: name.replace(/^[▾▸]\s*/, '') }).first()).toHaveAttribute('data-open', '0');
  expect(await view.locator('[data-unit-row]').count()).toBeLessThan(rows);
  // сортировка без нового запроса
  await openFilters(view);
  await view.locator('#sb-sort').selectOption('label');
  await expect(view.locator('#sb-sort')).toHaveValue('label');
  await openFilters(view);
  await view.locator('#sb-grouped').uncheck();
  await expect(view.locator('[data-sec]')).toHaveCount(0);
  // листание месяца и «Сегодня»
  const label = (await view.locator('#sm-label').textContent()).trim();
  await view.locator('#sm-next').click();
  await expect(view.locator('#sm-label')).not.toHaveText(label);
  await expect(view.locator('.sb-grid')).toBeVisible();
  await view.locator('#sm-today').click();
  await expect(view.locator('#sm-label')).toHaveText(label);
  expect(errors).toEqual([]);
});

test('панель фильтров: поиск не теряет фокус и текст, фильтр по категории сужает, «Сбросить»', async ({ page }) => {
  const errors = watchErrors(page);
  await login(page, 'admin');
  await open(page, 'stays');
  const view = page.locator('#view-stays');
  await expect(view.locator('.sb-grid')).toBeVisible();
  const total = await view.locator('[data-unit-row]').count();
  // поиск: фокус и каретка остаются в поле после перерисовки вида
  const q = view.locator('#sf-q');
  await q.click();
  await page.keyboard.type('Орлов', { delay: 60 });
  await page.waitForTimeout(900);
  await expect(q).toBeFocused();
  await expect(q).toHaveValue('Орлов');
  await expect(view.locator('.sb-grid')).toBeVisible();
  await view.locator('#sf-reset').click();
  await expect(q).toHaveValue('');
  // категория
  await openFilters(view);
  await view.locator('[data-sf-dd=cat] summary').click();
  const first = view.locator('[data-sf-cat]').first();
  await first.check();
  await expect.poll(async () => view.locator('[data-unit-row]').count()).toBeLessThan(total);
  await expect(view.locator('[data-sf-dd=cat] summary b')).not.toHaveText('все');
  await view.locator('#sf-reset').click();
  await expect.poll(async () => view.locator('[data-unit-row]').count()).toBe(total);
  expect(errors).toEqual([]);
});

test('мобильный счётчик фильтров принадлежит кнопке и шаблон не печатает комментарий', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await login(page, 'admin');
  await open(page, 'stays');
  const view = page.locator('#view-stays');
  const toggle = view.locator('.sf-toggle');
  await toggle.click();
  await openFilters(view);
  await view.locator('[data-sf-dd=cat] summary').click();
  await view.locator('[data-sf-cat]').first().check();
  await expect(toggle.locator('b')).toHaveText('(1)');
  await toggle.locator('b').click();
  await expect(toggle).toHaveAttribute('aria-expanded', 'false');
  await expect(view.locator('.sf-panel')).not.toHaveClass(/open/);
  await expect(view).not.toContainText('на телефоне создание брони — плавающая кнопка');
});

test('сохранённые наборы фильтров: сохранить, выбрать, удалить', async ({ page }) => {
  const errors = watchErrors(page);
  await login(page, 'admin');
  await open(page, 'stays');
  const view = page.locator('#view-stays');
  await openFilters(view);
  await expect(view.locator('.sf-panel')).toBeVisible();
  await openFilters(view);
  await view.locator('[data-sf-dd=cat] summary').click();
  await view.locator('[data-sf-cat]').first().check();
  await expect(view.locator('[data-sf-dd=cat] summary b')).not.toHaveText('все');   // вид перерисован — панель знает фильтр
  await view.locator('#sf-save-name').fill('мой набор');
  await view.locator('#sf-save').click();
  await expect(view.locator('#sf-saved option[value="мой набор"]')).toBeAttached();
  await view.locator('#sf-reset').click();
  await openFilters(view);
  await view.locator('#sf-saved').selectOption('мой набор');
  await expect(view.locator('[data-sf-dd=cat] summary b')).not.toHaveText('все');
  await view.locator('#sf-del').click();
  await expect(view.locator('#sf-saved option[value="мой набор"]')).toHaveCount(0);
  expect(errors).toEqual([]);
});

test('батлеры, табло дня и загрузка: сетки, счётчики, переходы', async ({ page }) => {
  const errors = watchErrors(page);
  await login(page, 'admin');
  await open(page, 'stays');
  const view = page.locator('#view-stays');
  await tab(page, 'butlers').click();
  await expect(view.locator('.bb-grid')).toBeVisible();
  await expect(view.locator('#stays-body')).toContainText('лимит нагрузки');
  // день батлера открывается окном
  const cell = view.locator('[data-bb-emp]').first();
  if (await cell.count()) {
    await cell.click();
    await expect(page.locator('#modal .modal-head h3')).toContainText('·');
    await page.locator('#modal [data-close]').click();
  }
  await tab(page, 'day').click();
  await expect(view.locator('.db-sum')).toBeVisible();
  await expect(view.locator('[data-dtab]')).toHaveCount(4);
  const date = await view.locator('#db-date').inputValue();
  await view.locator('#db-prev').click();
  await expect(view.locator('#db-date')).not.toHaveValue(date);
  await view.locator('#db-today').click();
  await expect(view.locator('#db-date')).toHaveValue(date);
  await view.locator('[data-dtab=in_house]').click();
  await expect(view.locator('[data-dtab=in_house]')).toHaveClass(/btn-primary/);
  await tab(page, 'occupancy').click();
  await expect(view.locator('.oc-grid')).toBeVisible();
  await expect(view.locator('[data-oc-toggle]').first()).toBeVisible();
  await view.locator('[data-oc-mode=count]').click();
  await expect(view.locator('[data-oc-mode=count]')).toHaveClass(/btn-primary/);
  await view.locator('[data-oc-toggle]').first().click();            // свернуть узел «Итого»
  await expect(view.locator('.oc-grid .oc-line').first()).toBeVisible();
  expect(errors).toEqual([]);
});

test('«Брони»: список, сортировка, свой период, карточка брони', async ({ page }) => {
  const errors = watchErrors(page);
  await login(page, 'admin');
  await open(page, 'stays');
  const view = page.locator('#view-stays');
  await tab(page, 'bookings').click();
  await expect(view.locator('#bk-total')).toContainText('Найдено броней');
  expect(await view.locator('tr.bk-row').count()).toBeGreaterThan(0);
  // сортировка по клику на заголовок: стрелка показывает направление
  await view.locator('th[data-bk-sort=number]').click();
  await expect(view.locator('th[data-bk-sort=number]')).toContainText('↑');
  await view.locator('th[data-bk-sort=number]').click();
  await expect(view.locator('th[data-bk-sort=number]')).toContainText('↓');
  // свой период: появляются поля дат
  await view.locator('#bk-period').selectOption('custom');
  await expect(view.locator('#bk-first')).toBeVisible();
  await expect(view.locator('#bk-last')).toBeVisible();
  // карточка брони по клику на строку
  await view.locator('#bk-period').selectOption('month');
  await view.locator('#bk-mode').selectOption('stay');
  const row = view.locator('tr.bk-row').first();
  await row.click();
  await expect(page.locator('#modal .modal-head h3')).toContainText('Бронь');
  await expect(page.locator('#modal')).toContainText('История изменений');
  await page.locator('#modal [data-close]').click();
  expect(errors).toEqual([]);
});

test('«Шахматка» и «Мои гости» под ролями; стирание раздела снаружи не ломает загрузку', async ({ page }) => {
  const errors = watchErrors(page);
  await login(page, 'rukovod');
  await open(page, 'stays');
  await expect(page.locator('#view-stays .sb-grid')).toBeVisible();
  await page.evaluate(() => document.querySelectorAll('.view').forEach(v => { v.innerHTML = ''; }));
  await open(page, 'stays');
  await expect(page.locator('#view-stays .sb-grid')).toBeVisible();
  await expect(page.locator('#view-stays [data-stab]').first()).toBeVisible();
  expect(errors).toEqual([]);
});

test('выгрузка шахматки передаёт месяц и фильтр в новый XLSX', async ({ page }) => {
  await login(page, 'admin');
  await open(page, 'stays');
  const view = page.locator('#view-stays');
  await expect(view.locator('.sb-grid')).toBeVisible();
  const button = view.locator('#sb-board-xlsx');
  await expect(button).toBeEnabled();
  await openFilters(view);
  await view.locator('[data-sf-dd=cat] summary').click();
  const box = view.locator('[data-sf-cat]').first();
  const category = await box.getAttribute('data-sf-cat');
  const board = page.waitForResponse(r => r.url().includes('/board/units?') &&
    new URL(r.url()).searchParams.get('category_ids') === category);
  await box.check();
  const expected = new URL((await board).url()).searchParams;
  const request = page.waitForRequest(r => r.url().includes('/board/units/export?'));
  const download = page.waitForEvent('download');
  await clickExport(view, button);
  const params = new URL((await request).url()).searchParams;
  expect(params.get('first')).toBe(expected.get('first'));
  expect(params.get('last')).toBe(expected.get('last'));
  expect(params.get('category_ids')).toBe(category);
  expect(params.get('format')).toBe('xlsx');
  expect((await download).suggestedFilename()).toBe(`shakhmatka_${params.get('first').slice(0, 7)}.xlsx`);
});

for (const expired of [false, true]) {
  test(`предпросмотр PDF закрывается при ${expired ? 'отзыве сессии сервером' : 'выходе'}`, async ({ page }) => {
    await login(page, 'admin');
    await page.route('**/api/stays/board/units/export?**', async route => {
      const marker = (await page.context().cookies()).find(c => c.name === 'tt_auth_context').value;
      expect(new URL(route.request().url()).searchParams.get('format')).toBe('pdf');
      expect(new URL(route.request().url()).searchParams.get('for_print')).toBe('true');
      await route.fulfill({ contentType: 'application/pdf', body: '%PDF-1.7',
        headers: { 'X-Butler-Auth-Context': marker } });
    });
    await page.evaluate(() => {
      const createObjectUrl = URL.createObjectURL.bind(URL);
      const blobs = new Map();
      URL.createObjectURL = blob => {
        const url = createObjectUrl(blob);
        if (blob.type === 'application/pdf') blobs.set(url, blob);
        return url;
      };
      window.open = () => {
        const preview = { closed: false, close() { this.closed = true; }, location: {
          replace(url) {
            blobs.get(url).text().then(data => { window.pdfContents = data; });
          },
        } };
        window.pdfPreview = preview;
        return preview;
      };
    });
    await open(page, 'stays');
    const action = page.locator('#sb-print');
    await expect(action).toBeEnabled();
    await clickExport(page.locator('#view-stays'), action);
    await expect.poll(() => page.evaluate(() => window.pdfContents)).toBe('%PDF-1.7');
    if (expired) {
      await page.route('**/api/auth/context', route => route.fulfill({ status: 401, json: {} }));
      await page.route('**/api/auth/me', route => route.fulfill({ status: 401, json: {} }));
      await page.evaluate(() => window.dispatchEvent(new Event('focus')));
    } else {
      await page.locator('#logout-btn').click();
    }
    await expect(page.locator('#login-screen')).toBeVisible();
    expect(await page.evaluate(() => window.pdfPreview.closed)).toBe(true);
  });
}
