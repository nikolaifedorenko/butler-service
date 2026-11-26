import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';
import { login, watchErrors } from './helpers.mjs';

test.use({ viewport: { width: 390, height: 844 } });

for (const scheme of ['light', 'dark']) {
  test(`состояние парка локальное и доступное в теме ${scheme}`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: scheme });
    await login(page, 'admin');
    const data = await (await page.request.get('/api/cars')).json();
    let release;
    const loading = new Promise(resolve => { release = resolve; });
    let available = false;
    await page.route('**/api/cars', async route => {
      await loading;
      if (available) await route.fulfill({ json: data });
      else await route.fulfill({ status: 503, json: { detail: 'Временный сбой' } });
    });
    await page.evaluate(() => window.navigate('cars'));
    const view = page.locator('#view-cars');
    try {
      const status = view.locator('[data-state="loading"]').getByRole('status');
      await expect(status).toContainText('Загружаем парк');
      await expect(page.locator('#loading')).toBeHidden();
    } finally {
      release();
    }
    const error = view.locator('[data-state="error"]');
    await expect(error).toContainText('Парк не загрузился');
    const retry = error.getByRole('button', { name: 'Повторить' });
    const size = await retry.boundingBox();
    expect(Math.round(size.height)).toBeGreaterThanOrEqual(44);
    await retry.focus();
    await expect(retry).toBeFocused();
    expect(await retry.evaluate(button => getComputedStyle(button).outlineStyle)).not.toBe('none');
    const { violations } = await new AxeBuilder({ page }).include('#view-cars [data-state="error"]')
      .withTags(['wcag2a', 'wcag2aa']).analyze();
    expect(violations.map(violation => violation.id)).toEqual([]);
    available = true;
    await page.keyboard.press('Enter');
    await expect(view.locator('#cars-list')).toBeFocused();
    await expect(view.locator('tbody [data-menu-btn]').first()).toBeVisible();
  });
}

test('пустой парк и фильтр без совпадений предлагают разные действия', async ({ page }) => {
  await login(page, 'admin');
  const data = await (await page.request.get('/api/cars')).json();
  let empty = true;
  await page.route('**/api/cars', route => route.fulfill({ json: { ...data, cars: empty ? [] : data.cars } }));
  await page.evaluate(() => window.navigate('cars'));
  const view = page.locator('#view-cars');
  await expect(view.locator('[data-state="empty"]')).toContainText('Парк пока пуст');
  await expect(view.locator('[data-state="filtered"]')).toHaveCount(0);
  empty = false;
  await view.getByRole('button', { name: 'Обновить' }).click();
  const search = view.getByRole('searchbox', { name: 'Поиск каров' });
  await search.fill('неттакогокара');
  const filtered = view.locator('[data-state="filtered"]');
  await expect(filtered).toContainText('Нет каров по фильтру');
  await filtered.getByRole('button', { name: 'Сбросить фильтры' }).click();
  await expect(search).toHaveValue('');
  await expect(view.locator('tbody [data-menu-btn]').first()).toBeVisible();
});

test('ошибка шахматки при смене месяца оставляет управление и даёт восстановить месяц', async ({ page }) => {
  const errors = watchErrors(page);
  await login(page, 'admin');
  let response = 'ready';
  await page.route('**/api/stays/board/units?*', route => {
    if (response === 'error') return route.fulfill({ status: 503, json: { detail: 'Временный сбой' } });
    if (response === 'maintenance') return route.fulfill({ contentType: 'text/html', body: '<h1>Maintenance</h1>' });
    return route.continue();
  });
  await page.evaluate(() => window.navigate('stays'));
  const view = page.locator('#view-stays');
  await expect(view.locator('.sb-grid [data-unit-row]').first()).toBeVisible();
  const initialPeriod = await view.locator('#sm-label').textContent();
  response = 'error';
  await view.getByRole('button', { name: 'Предыдущий месяц' }).click();
  const error = view.locator('[data-state="error"]');
  await expect(error).toContainText('Шахматка не загрузилась');
  await expect(view.getByRole('button', { name: 'Предыдущий месяц' })).toBeVisible();
  await expect(view.locator('#sm-label')).not.toHaveText(initialPeriod);
  const retry = error.getByRole('button', { name: 'Повторить' });
  response = 'maintenance';
  await retry.click();
  await expect(error).toContainText('Шахматка не загрузилась');
  await expect(view.locator('.sb-grid')).toBeHidden();
  response = 'ready';
  await retry.focus();
  await page.keyboard.press('Enter');
  await expect(view.locator('.sb-grid [data-unit-row]').first()).toBeVisible();
  await expect(view.locator('#sm-label')).toBeFocused();
  expect(errors.filter(error => !/^503 .*\/api\/stays\/board\/units\?/.test(error))).toEqual([]);
});

test('«Сегодня» повторяет запрос после сбоя загрузки текущего месяца', async ({ page }) => {
  await login(page, 'admin');
  let fail = false;
  await page.route('**/api/stays/board/units?*', route => fail
    ? route.fulfill({ status: 503, json: { detail: 'Временный сбой' } }) : route.continue());
  await page.evaluate(() => window.navigate('stays'));
  const view = page.locator('#view-stays');
  const period = view.locator('#sm-label');
  const initial = await period.textContent();
  await view.getByRole('button', { name: 'Предыдущий месяц' }).click();
  await expect(period).not.toHaveText(initial);
  await expect(view.locator('[data-state="loading"]')).toHaveCount(0);
  fail = true;
  await view.locator('#sm-today').click();
  await expect(view.locator('[data-state="error"]')).toBeVisible();
  fail = false;
  await view.locator('#sm-today').click();
  await expect(view.locator('.sb-grid [data-unit-row]').first()).toBeVisible();
  await expect(period).toHaveText(initial);
});

test('фоновое обновление не заменяет ручной повтор загрузки парка', async ({ page }) => {
  await login(page, 'admin');
  const data = await (await page.request.get('/api/cars')).json();
  let release, started;
  const ready = new Promise(resolve => { started = resolve; });
  const pending = new Promise(resolve => { release = resolve; });
  let attempts = 0;
  await page.route('**/api/cars', async route => {
    if (++attempts === 2) {
      started();
      await pending;
      await route.fulfill({ json: data });
    } else await route.fulfill({ status: 503, json: { detail: 'Временный сбой' } });
  });
  await page.evaluate(() => window.navigate('cars'));
  const view = page.locator('#view-cars');
  await view.locator('[data-state="error"] button').click();
  try {
    await ready;
    await page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')));
  } finally {
    release();
  }
  await expect(view.locator('#cars-list')).toBeVisible();
  expect(attempts).toBe(2);
});

test('поиск шахматки без броней сохраняет строки объектов и очищается отдельно', async ({ page }) => {
  await login(page, 'admin');
  await page.evaluate(() => window.navigate('stays'));
  const view = page.locator('#view-stays');
  const search = view.locator('#sf-q');
  await search.fill('гостькотороготочнонет');
  const state = view.locator('[data-state="filtered"]');
  await expect(state).toContainText('Броней по поиску нет');
  await expect(view.locator('.sb-grid [data-unit-row]').first()).toBeVisible();
  await state.getByRole('button', { name: 'Очистить поиск' }).click();
  await expect(search).toHaveValue('');
  await expect(search).toBeFocused();
});

test('«Сегодня» подписывает загрузку присутствия, пока сервер готовит данные', async ({ page }) => {
  let release;
  const pending = new Promise(resolve => { release = resolve; });
  await page.route('**/api/presence/board', async route => { await pending; await route.continue(); });
  await login(page, 'admin');
  try {
    await expect(page.locator('#view-today [data-state="loading"]').getByRole('status')).toHaveText('Загружаем присутствие…');
  } finally {
    release();
  }
  await expect(page.locator('#view-today [data-stat="at-work"]')).toBeVisible();
});

test('при уменьшенном движении переход к сегодняшней дате не прокручивается плавно', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.addInitScript(() => {
    const original = Element.prototype.scrollTo;
    window.boardScroll = [];
    Element.prototype.scrollTo = function (...args) {
      if (this.classList.contains('sb-grid')) window.boardScroll.push(args[0]?.behavior);
      return original.apply(this, args);
    };
  });
  await login(page, 'admin');
  await page.evaluate(() => window.navigate('stays'));
  const view = page.locator('#view-stays');
  await view.locator('#sm-today').click();
  const calls = await page.evaluate(() => window.boardScroll);
  expect(calls.length).toBeGreaterThan(0);
  expect(calls).not.toContain('smooth');
});

test('витрина показывает рабочие состояния под политикой безопасности страницы', async ({ page }) => {
  await page.goto('/static/design.html');
  const showcase = page.locator('#ds-data-states');
  await expect(showcase.locator('[data-state]')).toHaveCount(4);
  await expect(showcase.getByRole('button', { name: 'Повторить' })).toBeVisible();
});
