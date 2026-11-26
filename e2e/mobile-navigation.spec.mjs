import { expect, test } from '@playwright/test';
import { login } from './helpers.mjs';

async function goMobile(page, user) {
  await page.setViewportSize({ width: 390, height: 844 });
  await login(page, user);
}

const tabs = page => page.locator('#tabbar [data-view]');
const pinnedIds = page => tabs(page).evaluateAll(buttons => buttons.map(button => button.dataset.view));

test('мобильные разделы настраиваются и сохраняются отдельно для каждой учётной записи', async ({ page }) => {
  await goMobile(page, 'ivanov');
  expect(await pinnedIds(page)).toEqual(['today', 'mystays', 'night', 'cars']);
  const sections = page.locator('#mobile-sections');
  await expect(sections).toHaveText('Разделы');
  await sections.click();
  const catalog = page.getByRole('dialog', { name: 'Разделы' });
  await expect(catalog.getByRole('button', { name: 'Сегодня' })).toHaveAttribute('aria-current', 'page');
  await expect(catalog.getByRole('button', { name: 'График' })).toBeVisible();
  await expect(catalog.getByRole('button', { name: 'Настройки' })).toHaveCount(0);
  await catalog.getByRole('button', { name: 'Настроить панель' }).click();
  const settings = page.getByRole('dialog', { name: 'Быстрые вкладки' });
  const first = settings.getByLabel('Первая вкладка');
  await expect(first.locator('option', { hasText: 'Настройки' })).toHaveCount(0);
  await first.selectOption('grafik');
  await settings.getByRole('button', { name: 'Сохранить' }).click();
  await expect(settings).toHaveCount(0);
  await page.keyboard.press('Escape');
  expect(await pinnedIds(page)).toEqual(['today', 'grafik', 'night', 'cars']);

  await page.reload();
  await expect(page.locator('#view-today')).toBeVisible();
  expect(await pinnedIds(page)).toEqual(['today', 'grafik', 'night', 'cars']);
  await page.locator('#logout-btn').click();
  await expect(page.locator('#login-form')).toBeVisible();
  await login(page, 'admin');
  expect(await pinnedIds(page)).toEqual(['today', 'stays', 'grafik', 'settings']);
});

test('каталог выделяет текущий незакреплённый раздел и сохраняет места быстрых вкладок', async ({ page }) => {
  await goMobile(page, 'ivanov');
  const before = await pinnedIds(page);
  const sections = page.locator('#mobile-sections');
  await sections.click();
  let catalog = page.getByRole('dialog', { name: 'Разделы' });
  await catalog.getByRole('button', { name: 'График' }).click();
  await expect(page.locator('#view-grafik')).toBeVisible();
  await expect(sections).toHaveClass(/\bactive\b/);
  await sections.click();
  catalog = page.getByRole('dialog', { name: 'Разделы' });
  await expect(catalog.getByRole('button', { name: 'График' })).toHaveAttribute('aria-current', 'page');
  expect(await pinnedIds(page)).toEqual(before);
});

test('пустой слот сохраняет позиции вкладок, а подписи вмещаются в панель на 320 px', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 700 });
  await login(page, 'ivanov');
  const night = page.locator('#tabbar [data-view="night"]');
  const initial = await night.boundingBox();
  await page.locator('#mobile-sections').click();
  const catalog = page.getByRole('dialog', { name: 'Разделы' });
  await catalog.getByRole('button', { name: 'Настроить панель' }).click();
  let settings = page.getByRole('dialog', { name: 'Быстрые вкладки' });
  await settings.getByLabel('Первая вкладка').selectOption('');
  await settings.getByRole('button', { name: 'Сохранить' }).click();
  await page.keyboard.press('Escape');
  expect((await night.boundingBox()).x).toBe(initial.x);
  const protruding = await page.locator('#tabbar button').evaluateAll(buttons => buttons.filter(button => {
    const range = document.createRange();
    range.selectNodeContents(button.querySelector('span'));
    const label = range.getBoundingClientRect(), box = button.getBoundingClientRect();
    return label.left < box.left || label.right > box.right;
  }).map(button => button.textContent.trim()));
  expect(protruding).toEqual([]);
  await page.reload();
  await page.locator('#mobile-sections').click();
  await catalog.getByRole('button', { name: 'Настроить панель' }).click();
  settings = page.getByRole('dialog', { name: 'Быстрые вкладки' });
  await expect(settings.getByLabel('Первая вкладка')).toHaveValue('');
  await expect(settings.getByLabel('Вторая вкладка')).toHaveValue('night');
  await expect(settings.getByLabel('Третья вкладка')).toHaveValue('cars');
});

test('карточка гостя открывает конкретную бронь прямо на «Сегодня» и восстанавливает фокус', async ({ page }) => {
  await goMobile(page, 'ivanov');
  const cards = page.locator('#view-today .today-card');
  const card = cards.first();
  await expect(card).toBeVisible();
  const id = await card.getAttribute('data-reservation');
  const cardResponse = page.waitForResponse('**/api/stays/reservations/' + id + '/card');
  await card.focus();
  await page.keyboard.press('Enter');
  const dialog = page.getByRole('dialog', { name: /Бронь/ });
  await expect(dialog).toBeVisible();
  expect((await cardResponse).ok()).toBeTruthy();
  await expect(page.locator('#view-today')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(card).toBeFocused();
});

test('право на своих гостей открывает краткую карточку без запроса общего списка броней', async ({ page }) => {
  await goMobile(page, 'ivanov');
  const card = page.locator('#view-today .today-card').first();
  await expect(card).toBeVisible();
  const guest = (await card.locator('.today-name').textContent()).split(/ VIP | и ещё /)[0].trim();
  const requests = [];
  page.on('request', request => {
    if (/\/api\/stays\/reservations\/.+\/card$/.test(request.url())) requests.push(request.url());
  });
  await page.evaluate(() => { window.state.perms = ['stays.mine']; });
  await card.click();
  const dialog = page.getByRole('dialog', { name: /Бронь/ });
  await expect(dialog).toContainText(guest);
  expect(requests).toEqual([]);
  await page.keyboard.press('Escape');
  await expect(card).toBeFocused();
});

test('запоздалая карточка брони не открывается поверх другого раздела', async ({ page }) => {
  await goMobile(page, 'ivanov');
  const card = page.locator('#view-today .today-card').first();
  await expect(card).toBeVisible();
  const id = await card.getAttribute('data-reservation');
  await page.evaluate(path => {
    const fetch = window.fetch.bind(window);
    const delay = new Promise(resolve => { window.releaseBookingResponse = resolve; });
    window.fetch = async (input, options) => {
      const response = await fetch(input, options);
      if (new URL(input, location.href).pathname === path) {
        window.bookingResponseWaiting = response.ok;
        await delay;
      }
      return response;
    };
  }, `/api/stays/reservations/${id}/card`);
  await card.click();
  await page.waitForFunction(() => window.bookingResponseWaiting === true);
  await page.locator('#tabbar [data-view="mystays"]').click();
  await expect(page.locator('#view-mystays')).toBeVisible();
  await page.evaluate(async () => {
    window.releaseBookingResponse();
    await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
  });
  await expect(page.getByRole('dialog', { name: /Бронь/ })).toHaveCount(0);
});

test('если бронь исчезла при обновлении, фокус возвращается к блоку «Мои гости»', async ({ page }) => {
  await goMobile(page, 'ivanov');
  const card = page.locator('#view-today .today-card').first();
  await card.click();
  await expect(page.getByRole('dialog', { name: /Бронь/ })).toBeVisible();
  await page.route('**/api/stays/mine/today', async route => {
    const response = await route.fetch();
    const data = await response.json();
    await route.fulfill({ response, json: { ...data, reservations: [] } });
  });
  await page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')));
  await expect(card).toHaveCount(0);
  await page.keyboard.press('Escape');
  await expect(page.locator('#view-today [data-today-ready="mine"]')).toBeFocused();
});
