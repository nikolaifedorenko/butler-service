/* «Сегодня» (шаг 6в-3): стартовый экран с блоками по правам. */
import { expect, test } from '@playwright/test';
import { login, watchErrors } from './helpers.mjs';

const today = page => page.locator('#view-today');

test('Today permissions follow normal impersonation and return to the seeded administrator', async ({ page }) => {
  // Use empty projection data for all three blocks.
  await page.route('**/api/presence/board', route => route.fulfill({ json: { at_work_now: 0, expected_now: 0, yet_to_come: [] } }));
  await page.route('**/api/punches/status', route => route.fulfill({ json: { on_shift: false } }));
  await page.route('**/api/stays/mine/today', route => route.fulfill({ json: { date: '2026-01-01', reservations: [] } }));
  await login(page, 'admin');
  await expect(today(page).locator('[data-stat=at-work]')).toBeVisible();
  await page.evaluate(() => window.navigate('employees'));
  await page.locator('#view-employees tr[data-card]').filter({ hasText: 'Иванов' }).first().click();
  await page.locator('#modal [data-imp]').click();
  await expect(page.locator('#view-me.active')).toBeVisible();
  await page.evaluate(() => window.navigate('today'));
  await expect(today(page).locator('[data-stat=mine]')).toBeVisible();
  await expect(today(page).locator('.today-shift')).toBeVisible();
  await expect(today(page).locator('[data-stat=at-work]')).toBeVisible(); // seeded employees have presence.view
  await page.locator('#stop-impersonation').click();
  await expect(today(page).locator('[data-stat=at-work]')).toBeVisible();
  await expect(today(page).locator('[data-stat=mine], .today-shift')).toHaveCount(0);
});

test('стартовый экран — «Сегодня» и первый пункт меню, приветствие и дата', async ({ page }) => {
  const errors = watchErrors(page);
  await login(page, 'ivanov');
  await expect(page.locator('#view-today.active')).toBeVisible();
  await expect(page.locator('#sidenav .nav-item').first()).toHaveAttribute('data-view', 'today');
  await expect(page.locator('#sidenav .nav-item.active')).toHaveAttribute('data-view', 'today');
  await expect(today(page).locator('.today-hello')).toContainText(/Доброй ночи|Доброе утро|Добрый день|Добрый вечер/);
  await expect(today(page).locator('.today-hello')).toContainText('Иван');
  await expect(today(page).locator('.today-date')).toContainText(/(Понедельник|Вторник|Среда|Четверг|Пятница|Суббота|Воскресенье), \d+ /);
  await expect(today(page)).not.toContainText('Загрузка…');
  expect(errors).toEqual([]);
});

test('батлер: сводка, «Сейчас важно» и отдельный переход в «Мои гости»', async ({ page }) => {
  const errors = watchErrors(page);
  await login(page, 'ivanov');
  const view = today(page);
  await expect(view.locator('[data-stat=mine], [data-stat=in], [data-stat=out]')).toHaveCount(3);
  const mine = Number(await view.locator('[data-stat=mine]').textContent());
  const arrivals = Number(await view.locator('[data-stat=in]').textContent());
  const departures = Number(await view.locator('[data-stat=out]').textContent());
  await expect(view.locator('.today-h').first()).toHaveText('Сейчас важно');
  // карточек столько же, сколько броней (одна из них может быть в «Сейчас важно»)
  expect(await view.locator('.today-card').count()).toBe(mine);
  if (arrivals + departures === 0) await expect(view.locator('[data-empty=important]')).toBeVisible();
  else await expect(view.locator('.today-card.urgent')).toHaveCount(1);
  expect(mine).toBeGreaterThan(0);
  await view.getByRole('button', { name: 'Все мои гости' }).click();
  await expect(page.locator('#view-mystays.active')).toBeVisible();
  expect(errors).toEqual([]);
});

test('руководитель: присутствие и переход в «Отметки»', async ({ page }) => {
  const errors = watchErrors(page);
  await login(page, 'admin');
  const view = today(page);
  await expect(view.locator('[data-stat=at-work]')).toBeVisible();
  await expect(view.locator('[data-stat=expected]')).toBeVisible();
  await expect(view.locator('[data-stat=late]')).toBeVisible();
  await expect(view.locator('[data-stat=mine]')).toHaveCount(0);        // у администратора нет сотрудника — блока гостей нет
  await view.getByRole('button', { name: /Открыть «Отметки»/ }).click();
  await expect(page.locator('#view-marks.active')).toBeVisible();
  expect(errors).toEqual([]);
});

test('сотрудник: смена и кнопка «Пришёл / Ушёл» работают с экрана «Сегодня»', async ({ page }) => {
  const errors = watchErrors(page);
  await login(page, 'gromova');
  const view = today(page);
  await expect(view.locator('.today-shift')).toBeVisible();
  // кнопка есть и когда смена есть, и когда её нет (тогда часы учтутся как переработка — как в «Моих отметках»)
  const btn = view.locator('#today-punch');
  await expect(btn).toBeVisible();
  const was = (await btn.textContent()).trim();
  await btn.click();
  await expect(view.locator('#today-punch')).not.toHaveText(was);
  if (was === 'Ушёл') {                              // после ухода предлагают описать переработку
    await expect(page.locator('#modal .modal-head h3')).toHaveText('Описание переработки');
    await page.locator('#modal [data-skip]').click();
  }
  expect(errors).toEqual([]);
});

test('на телефоне три показателя в один ряд и шапка без горизонтальной прокрутки', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await login(page, 'ivanov');
  const view = today(page);
  await expect(view.locator('[data-stat=mine]')).toBeVisible();
  const tops = await view.locator('.today-stats').first().locator('.stat').evaluateAll(els => els.map(e => Math.round(e.getBoundingClientRect().top)));
  expect(new Set(tops).size).toBe(1);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test('после стирания раздела снаружи (смена пользователя) экран рисуется заново', async ({ page }) => {
  const errors = watchErrors(page);
  await login(page, 'ivanov');
  await expect(today(page).locator('.today-hello')).toBeVisible();
  await page.evaluate(() => document.querySelectorAll('.view').forEach(v => { v.innerHTML = ''; }));
  await page.evaluate(() => window.navigate('today'));
  await expect(today(page).locator('.today-hello')).toBeVisible();
  expect(errors).toEqual([]);
});

const todayBlocks = [
  ['**/api/punches/status', { shift: null, on_shift: false }],
  ['**/api/stays/mine/today', { date: '2026-11-26', reservations: [] }],
  ['**/api/presence/board', { at_work_now: 3, expected_now: 4, yet_to_come: [] }],
];

test('сбой блока гостей оставляет смену и присутствие и позволяет повторить только поиск гостей', async ({ page }) => {
  let guestsAvailable = false;
  const calls = new Map();
  for (const [path, payload] of todayBlocks) {
    await page.route(path, route => {
      calls.set(path, (calls.get(path) || 0) + 1);
      if (path.includes('/mine/') && !guestsAvailable) return route.fulfill({ status: 503, json: { detail: 'fixture' } });
      return route.fulfill({ json: payload });
    });
  }
  await login(page, 'ivanov');
  const view = today(page);
  const error = view.locator('[data-today-error="mine"]');
  await expect(error).toContainText('Не удалось загрузить гостей');
  await expect(view.locator('#today-punch')).toBeVisible();
  await expect(view.locator('[data-stat=at-work]')).toHaveText('3');
  const beforeRetry = todayBlocks.map(([path]) => calls.get(path));

  guestsAvailable = true;
  await error.getByRole('button', { name: 'Повторить' }).click();
  await expect(view.locator('[data-stat=mine]')).toBeVisible();
  await expect(error).toHaveCount(0);
  expect(todayBlocks.map(([path]) => calls.get(path))).toEqual([
    beforeRetry[0], beforeRetry[1] + 1, beforeRetry[2],
  ]);
});

test('при полном сбое на «Сегодня» одно действие повтора всех блоков', async ({ page }) => {
  let available = false;
  for (const [path, payload] of todayBlocks) {
    await page.route(path, route => available
      ? route.fulfill({ json: payload })
      : route.fulfill({ status: 503, json: { detail: 'fixture' } }));
  }
  await login(page, 'ivanov');
  const view = today(page);
  const error = view.locator('[data-today-error="all"]');
  await expect(error).toContainText('Не удалось загрузить данные на сегодня');
  await expect(view.getByRole('button', { name: 'Повторить' })).toHaveCount(1);
  await expect(view.locator('.today-shortcuts')).toHaveCount(0);
  available = true;
  await error.getByRole('button', { name: 'Повторить' }).click();
  await expect(view.locator('#today-punch')).toBeVisible();
  await expect(view.locator('[data-stat=mine]')).toBeVisible();
  await expect(view.locator('[data-stat=at-work]')).toBeVisible();
  await expect(error).toHaveCount(0);
});

test('пояснение о переработке показывается рядом с отметкой вне графика', async ({ page }) => {
  let shift = null;
  await page.route('**/api/punches/status', route => route.fulfill({ json: { on_shift: false, shift } }));
  await login(page, 'ivanov');
  const strip = today(page).locator('.today-shift');
  await expect(strip.getByRole('button', { name: 'Пришёл' })).toBeVisible();
  await expect(strip).toContainText('Часы будут учтены как переработка');

  shift = { start_hm: '08:00', end_hm: '20:00' };
  await page.evaluate(() => window.navigate('today'));
  await expect(strip).toContainText('Смена 08:00–20:00');
  await expect(strip).not.toContainText('Часы будут учтены как переработка');
});

test('старый ответ статуса не откатывает уже принятую отметку', async ({ page }) => {
  await page.clock.install();
  let holdStatus = false;
  const arrived = Promise.withResolvers();
  const release = Promise.withResolvers();
  await page.route('**/api/punches/status', async route => {
    if (holdStatus) {
      arrived.resolve();
      await release.promise;
      holdStatus = false;
    }
    await route.fulfill({ json: { on_shift: false } });
  });
  await page.route('**/api/punches', route => route.fulfill({
    json: { message: 'Отметка принята', status: { on_shift: true, session_start: '2026-11-26T10:00:00+03:00' } },
  }));
  await login(page, 'ivanov');
  const button = today(page).locator('#today-punch');
  await expect(button).toHaveText('Пришёл');
  holdStatus = true;
  await page.clock.fastForward(31_000);
  await arrived.promise;
  const oldStatus = page.waitForResponse('**/api/punches/status');
  try {
    await button.click();
    await expect(button).toHaveText('Ушёл');
  } finally {
    release.resolve();
  }
  await (await oldStatus).finished();
  // После обработки старого ответа проставленный сервером статус должен сохраниться.
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  await expect(button).toHaveText('Ушёл');
});

test('медленный блок гостей не скрывает уже загруженную смену и присутствие', async ({ page }) => {
  const arrived = Promise.withResolvers();
  const release = Promise.withResolvers();
  for (const [path, payload] of todayBlocks) {
    await page.route(path, async route => {
      if (!path.includes('/mine/')) return route.fulfill({ json: payload });
      arrived.resolve();
      await release.promise;
      return route.fulfill({ status: 503, json: { detail: 'fixture' } });
    });
  }
  await login(page, 'ivanov');
  const view = today(page);
  await arrived.promise;
  try {
    await expect(view.locator('#today-punch')).toBeVisible();
    await expect(view.locator('[data-stat=at-work]')).toHaveText('3');
    await expect(view.locator('[data-today-error="all"]')).toHaveCount(0);
  } finally {
    release.resolve();
  }
  await expect(view.locator('[data-today-error="mine"]')).toBeVisible();
});

test('повтор с клавиатуры удерживает фокус до загрузки и переводит его к результату', async ({ page }) => {
  let retry = false;
  const arrived = Promise.withResolvers();
  const release = Promise.withResolvers();
  for (const [path, payload] of todayBlocks) {
    await page.route(path, async route => {
      if (!path.includes('/mine/')) return route.fulfill({ json: payload });
      if (!retry) return route.fulfill({ status: 503, json: { detail: 'fixture' } });
      arrived.resolve();
      await release.promise;
      return route.fulfill({ json: payload });
    });
  }
  await login(page, 'ivanov');
  const view = today(page);
  const action = view.locator('[data-today-error="mine"] button');
  retry = true;
  await action.focus();
  await page.keyboard.press('Enter');
  await arrived.promise;
  try {
    await expect(action).toBeFocused();
    await expect(action).toHaveAttribute('aria-disabled', 'true');
  } finally {
    release.resolve();
  }
  await expect(view.getByRole('heading', { name: 'Мои гости' })).toBeFocused();
});

test('некорректный ответ гостей показывает ошибку только в их блоке', async ({ page }) => {
  for (const [path, payload] of todayBlocks) {
    await page.route(path, route => path.includes('/mine/')
      ? route.fulfill({ contentType: 'text/html', body: '<h1>Технические работы</h1>' })
      : route.fulfill({ json: payload }));
  }
  await login(page, 'ivanov');
  const view = today(page);
  await expect(view.locator('[data-today-error="mine"]')).toContainText('Не удалось загрузить гостей');
  await expect(view.locator('#today-punch')).toBeVisible();
  await expect(view.locator('[data-stat=at-work]')).toHaveText('3');
});
