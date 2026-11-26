import { expect, test } from '@playwright/test';
import { login } from './helpers.mjs';

const internal = /\bv7\.1\b|\b(?:CFG|RUL|CHK|INV)-[A-Z*]|\b(?:getMe|getUpdates|payload)\b|версия\s*#\d+|слой\s*[0-3]/i;

test('экран входа представляет рабочее место и оставляет поля пустыми', async ({ page }) => {
  await page.goto('/');
  const loginScreen = page.locator('#login-screen');
  await expect(loginScreen.getByRole('heading', { name: 'Батлер Сервис' })).toBeVisible();
  await expect(loginScreen.getByText('Рабочее место батлерской службы')).toBeVisible();
  await expect(loginScreen.getByLabel('Логин')).toHaveValue('');
  await expect(loginScreen.getByLabel('Пароль')).toHaveValue('');
  await expect(loginScreen.getByRole('button', { name: 'Войти', exact: true })).toBeVisible();
});

test('График описывает задачи четырёх вкладок понятными названиями', async ({ page }) => {
  await login(page, 'admin');
  await page.evaluate(() => window.navigate('grafik'));
  const tabs = page.locator('#grafik-tabs');
  for (const [name, sub] of [
    ['Табель', 'Коды дней и плановые часы'],
    ['План смен', 'Предстоящие смены'],
    ['Факт', 'Отметки и отработанное время'],
    ['Управленческий табель', 'Итоги часов и закрытие периода'],
  ]) {
    const tab = tabs.getByRole('button', { name: name + ' ' + sub, exact: true });
    await expect(tab).toBeVisible();
    await tab.click();
    await expect(tab).toHaveAttribute('aria-current', 'true');
    const heading = page.locator('#view-grafik .layer-pane.on .page-head').first();
    await expect(heading.getByRole('heading', { name, exact: true })).toBeVisible();
    await expect(heading).not.toContainText(internal);
  }
  await expect(tabs).not.toContainText(internal);
});

test('справочники, правила и уведомления используют рабочие названия', async ({ page }) => {
  await login(page, 'admin');
  await page.evaluate(() => window.navigate('settings'));
  const nav = page.locator('#st-nav');
  const body = page.locator('#st-body');
  for (const [id, heading] of [['overview', 'Обзор'], ['calc', 'Расчёт'], ['codes', 'Коды Табеля'],
    ['pay', 'Правила оплаты'], ['groups', 'Группы и графики'], ['system', 'Система'], ['notify', 'Чаты и Почта']]) {
    await nav.locator('[data-st="' + id + '"]').click();
    await expect(body.getByRole('heading', { name: heading, exact: true, level: 2 })).toBeVisible();
    await expect(body).not.toContainText(internal);
  }
  await expect(nav).not.toContainText(internal);
  await expect(body.getByRole('button', { name: 'Проверить бота', exact: true })).toBeVisible();
  await expect(body.getByRole('button', { name: 'Обновить список чатов', exact: true })).toBeVisible();
});

test('предупреждение о состоянии приложения подсказывает действие без вывода диагностики', async ({ page }) => {
  await page.route('**/api/selfcheck', route => route.fulfill({ json: {
    ok: false, hint: 'Схема БД', missing: ['CREATE INDEX internal_index'], details: 'SQLSTATE 23505',
  } }));
  await login(page, 'admin');
  const banner = page.locator('#schema-banner');
  await expect(banner).toContainText('Обратитесь к администратору');
  await expect(banner).not.toContainText(/CREATE INDEX|SQLSTATE|Схема БД/);
  await banner.getByRole('button', { name: 'Скрыть' }).click();
  await expect(banner).toBeHidden();
});

test('ответ проверки системы не открывает окно после перехода в другой раздел настроек', async ({ page }) => {
  await login(page, 'admin');
  await page.evaluate(() => window.navigate('settings'));
  const nav = page.locator('#st-nav');
  await nav.locator('[data-st="system"]').click();
  const received = Promise.withResolvers(), release = Promise.withResolvers();
  await page.route('**/api/selfcheck', async route => {
    received.resolve();
    await release.promise;
    await route.fulfill({ json: { ok: true } });
  });
  const check = page.getByRole('button', { name: 'Проверить состояние системы' });
  await check.click();
  await received.promise;
  const response = page.waitForResponse('**/api/selfcheck');
  try {
    await nav.locator('[data-st="calc"]').click();
  } finally {
    release.resolve();
  }
  await (await response).finished();
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  await expect(page.getByRole('heading', { name: 'Расчёт', exact: true })).toBeVisible();
  await expect(page.getByRole('dialog')).toHaveCount(0);
});

test('на 320 px названия и подписи Графика помещаются в два ряда', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 700 });
  await login(page, 'admin');
  await page.evaluate(() => window.navigate('grafik'));
  const tabs = page.locator('#grafik-tabs button');
  await expect(tabs).toHaveCount(4);
  const layout = await tabs.evaluateAll(buttons => buttons.map(button => {
    const rect = button.getBoundingClientRect();
    return {
      top: rect.top,
      fits: rect.left >= 0 && rect.right <= window.innerWidth && button.scrollWidth <= button.clientWidth,
      height: rect.height,
      description: Boolean(button.querySelector('small')?.getBoundingClientRect().height),
    };
  }));
  expect(new Set(layout.map(tab => tab.top)).size).toBe(2);
  expect(layout.every(tab => tab.fits && tab.height >= 44 && tab.description)).toBe(true);
});
