import { expect, test } from '@playwright/test';
import { login } from './helpers.mjs';

const phone = { width: 390, height: 844 };
const dayLink = page => page.locator('#view-today').getByRole('button', { name: 'Табло дня', exact: true });
const board = page => page.locator('#view-stays');
const openBoard = page => page.locator('#tabbar [data-view="stays"]').click();
const openToday = page => page.locator('#tabbar [data-view="today"]').click();
const propertyDate = page => page.evaluate(async () => (await import('/static/js/core.js')).todayISO());

test('старший батлер попадает на табло текущего дня, обычный вход ведёт к объектам', async ({ page }) => {
  await page.setViewportSize(phone);
  await login(page, 'gromova');
  let release;
  const pending = new Promise(resolve => { release = resolve; });
  await page.route(url => url.pathname === '/api/stays/day', async route => { await pending; await route.continue(); });
  const link = dayLink(page);
  await expect(link).toBeInViewport();
  await link.focus();
  await page.keyboard.press('Enter');
  const dayTab = board(page).getByRole('button', { name: 'Табло дня', exact: true });
  try {
    await expect(dayTab).toBeFocused();
    await expect(board(page).locator('[data-state="loading"]')).toBeVisible();
  } finally {
    release();
  }
  await expect(board(page).locator('#db-date')).toHaveValue(await propertyDate(page));
  await openToday(page);
  await openBoard(page);
  await expect(board(page).locator('.sb-grid [data-unit-row]').first()).toBeVisible();
  await expect(board(page).locator('#db-date')).toHaveCount(0);
});

test('быстрый переход использует сегодня, сохраняя дату обычного табло', async ({ page }) => {
  await page.setViewportSize(phone);
  await login(page, 'gromova');
  await openBoard(page);
  await board(page).getByRole('button', { name: 'Табло дня', exact: true }).click();
  const input = board(page).locator('#db-date');
  await expect(input).toBeVisible();
  const today = await propertyDate(page);
  await board(page).locator('#db-prev').click();
  await expect(input).not.toHaveValue(today);
  const priorDate = await input.inputValue();
  await openToday(page);
  await dayLink(page).click();
  await expect(input).toHaveValue(today);
  await openToday(page);
  await openBoard(page);
  await expect(input).toHaveValue(priorDate);
});

test('ссылка ограничена телефоном и ролью старшего батлера', async ({ page }) => {
  await login(page, 'gromova');
  await expect(page.locator('#view-today')).toBeVisible();
  await expect(dayLink(page)).toBeHidden();
  await page.setViewportSize(phone);
  await expect(dayLink(page)).toBeVisible();
  await page.evaluate(() => {
    window.state.perms = window.state.perms.filter(permission => permission !== 'stays.view');
    window.navigate('today');
  });
  await expect(dayLink(page)).toHaveCount(0);
  await page.locator('#logout-btn').click();
  await login(page, 'ivanov');
  await expect(page.locator('#view-today')).toBeVisible();
  await expect(dayLink(page)).toHaveCount(0);
});

test('быстрый и обычный пути дают те же заезд, выезд и бронь без батлера', async ({ page }) => {
  await page.setViewportSize(phone);
  await login(page, 'gromova');
  const date = await propertyDate(page);
  const { totals, visibility } = await (await page.request.get('/api/stays/day?date=' + date)).json();
  const row = (id, time, name, cover_status) => ({
    reservation_id: id, time, unit: 'Вилла', status: 'confirmed', cover_status, covered: [{ name: 'Дежурный', guests: [] }],
    guests: [{ name, role: 'main', relatives: [] }],
  });
  await page.route(url => url.pathname === '/api/stays/day', route => route.fulfill({ json: {
    date, totals, visibility, arrivals: [row(10, '08:30', 'Утренний заезд', 'covered'), row(11, '10:15', 'Поздний заезд', 'covered')],
    departures: [row(12, '09:00', 'Ближайший выезд', 'covered')], in_house: [], no_show: [],
    attention: [row(13, '09:45', 'Гость без батлера', 'uncovered')],
  } }));
  async function readTasks() {
    const first = board(page).locator('.db-list .db-row').first();
    await expect(first).toContainText('08:30');
    await expect(first).toContainText('Утренний заезд');
    await board(page).locator('[data-dtab="departures"]').click();
    await expect(first).toContainText('Ближайший выезд');
    await board(page).locator('[data-dtab="attention"]').click();
    await expect(first).toContainText('Гость без батлера');
    await expect(first).toContainText('не назначено');
  }
  await openBoard(page);
  await board(page).getByRole('button', { name: 'Табло дня', exact: true }).click();
  await readTasks();
  await openToday(page);
  await dayLink(page).click();
  await readTasks();
});

test.describe('телефон в другом часовом поясе', () => {
  test.use({ timezoneId: 'Pacific/Kiritimati' });

  test('быстрый вход запрашивает день по часам объекта у сервера', async ({ page }) => {
    await page.setViewportSize(phone);
    const health = await (await page.request.get('/api/health')).json();
    await login(page, 'gromova');
    const day = page.waitForResponse(response => new URL(response.url()).pathname === '/api/stays/day');
    await dayLink(page).click();
    const response = await day;
    expect(new URL(response.url()).searchParams.has('date')).toBe(false);
    expect(response.ok()).toBeTruthy();
    await expect(board(page).locator('#db-date')).toHaveValue(health.server_time_local.slice(0, 10));
  });
});
