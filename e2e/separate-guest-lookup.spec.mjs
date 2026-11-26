import { expect, test } from '@playwright/test';
import { login } from './helpers.mjs';

const board = page => page.locator('#view-stays');
const find = page => board(page).getByRole('button', { name: 'Найти гостя', exact: true });
const dialog = page => page.getByRole('dialog', { name: 'Найти гостя' });

test('поиск гостя открывается отдельно и сохраняет период и фильтры после карточки', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await login(page, 'admin');
  await page.evaluate(() => window.navigate('stays'));
  const view = board(page);
  await view.getByRole('button', { name: 'Предыдущий месяц' }).click();
  await expect(view.locator('[data-state="loading"]')).toHaveCount(0);
  const currentPeriod = await view.locator('#sm-label').textContent();
  const filter = view.getByRole('searchbox', { name: 'Фильтр текущего вида' });
  await filter.fill('Орлов');
  await view.locator('.sf-toggle').click();
  const group = view.locator('[data-sf-dd="group"]');
  await group.locator('summary').click();
  const selected = group.locator('input[data-sf-group]').first();
  await selected.check();
  await expect(selected).toBeChecked();
  await find(page).click();
  const search = dialog(page).getByRole('searchbox');
  await expect(search).toBeFocused();
  await search.fill('Орлов');
  await dialog(page).locator('[data-sg-guest]').first().click();
  await expect(page.locator('#drawer')).toBeVisible();
  await expect(dialog(page)).toHaveCount(0);
  await page.keyboard.press('Escape');
  await expect(find(page)).toBeFocused();
  await expect(view.locator('#sm-label')).toHaveText(currentPeriod);
  await expect(filter).toHaveValue('Орлов');
  await expect(selected).toBeChecked();
});

test('отдельный поиск сохраняет ограничение «только свои» и сообщает об ошибке отдельно', async ({ page }) => {
  await login(page, 'ivanov');
  await page.evaluate(() => {
    window.state.perms = window.state.perms.filter(permission => permission !== 'stays.guests');
    window.navigate('stays');
  });
  let available = false;
  let query;
  await page.route(url => url.pathname === '/api/stays/guests', route => {
    query = new URL(route.request().url()).searchParams;
    return available ? route.fulfill({ json: [] })
      : route.fulfill({ status: 503, json: { detail: 'Временный сбой' } });
  });
  await find(page).click();
  await dialog(page).getByRole('searchbox').fill('Орлов');
  const status = dialog(page).locator('[data-state="error"]');
  await expect(status).toContainText('Поиск не загрузился');
  expect(query.get('mine')).toBe('1');
  available = true;
  await status.getByRole('button', { name: 'Повторить' }).click();
  await expect(dialog(page).locator('[data-state="filtered"]')).toContainText('Гостей не найдено');
  await page.keyboard.press('Escape');
  await expect(find(page)).toBeFocused();
});

test('роль с видом занятости не получает отдельный поиск и фильтр по гостю', async ({ page }) => {
  await login(page, 'sluzhba');
  await page.evaluate(() => window.navigate('stays'));
  await expect(board(page).locator('.sb-grid')).toBeVisible();
  await expect(find(page)).toHaveCount(0);
  await expect(board(page).locator('#sf-q')).toHaveCount(0);
});

test('отложенная карточка гостя не перекрывает активную палитру команд', async ({ page }) => {
  await login(page, 'admin');
  await page.evaluate(() => window.navigate('stays'));
  await find(page).click();
  await dialog(page).getByRole('searchbox').fill('Орлов');
  const result = dialog(page).locator('[data-sg-guest]').first();
  const id = await result.getAttribute('data-sg-guest');
  const path = `/api/stays/guests/${id}/card`;
  const data = await (await page.request.get(path)).json();
  let started, release;
  const request = new Promise(resolve => { started = resolve; });
  const pending = new Promise(resolve => { release = resolve; });
  await page.route(url => url.pathname === path, async route => {
    started();
    await pending;
    await route.fulfill({ json: data });
  });
  await result.click();
  const commands = page.getByRole('dialog', { name: 'Команды' });
  const refreshed = page.waitForResponse(response => new URL(response.url()).pathname === '/api/stays/guests');
  try {
    await request;
    await page.keyboard.press('ControlOrMeta+k');
    await expect(commands).toBeVisible();
  } finally {
    release();
  }
  // This follow-up query starts only after the card response was processed and discarded.
  await (await refreshed).finished();
  await expect(commands).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(dialog(page).locator('[data-sg-guest]').first()).toBeVisible();
  await expect(page.locator('#drawer')).toBeHidden();
});

test('загрузка редактора не открывает окно после закрытия карточки гостя', async ({ page }) => {
  await login(page, 'admin');
  await page.evaluate(() => window.navigate('stays'));
  await find(page).click();
  await dialog(page).getByRole('searchbox').fill('Орлов');
  const result = dialog(page).locator('[data-sg-guest]').first();
  const id = await result.getAttribute('data-sg-guest');
  const path = `/api/stays/guests/${id}`;
  const payload = await (await page.request.get(path)).json();
  let started, release;
  const pending = new Promise(resolve => { release = resolve; });
  const request = new Promise(resolve => { started = resolve; });
  await page.route(url => url.pathname === path, async route => {
    started();
    await pending;
    await route.fulfill({ json: payload });
  });
  const response = page.waitForResponse(r => new URL(r.url()).pathname === path);
  await result.click();
  const drawer = page.locator('#drawer');
  await drawer.getByRole('button', { name: 'Изменить профиль' }).click();
  try {
    await request;
    await page.keyboard.press('Escape');
    await expect(drawer).toBeHidden();
    await expect(find(page)).toBeFocused();
  } finally {
    release();
  }
  await response;
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  await expect(page.locator('#modal #gf-last')).toHaveCount(0);
  await expect(find(page)).toBeFocused();
});
