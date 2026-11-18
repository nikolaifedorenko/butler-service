/* «Настройки»: оболочка, переходы между экранами, поиск ⌘K, черновик (шаг 6ж-1). */
import { expect, test } from '@playwright/test';
import { login, watchErrors } from './helpers.mjs';

const open = (page, view) => page.evaluate(v => window.navigate(v), view);

test('оболочка Настроек: навигация по экранам без ошибок и подсветка текущего', async ({ page }) => {
  const errors = watchErrors(page);
  await login(page, 'admin');
  await open(page, 'settings');
  const view = page.locator('#view-settings');
  await expect(view.locator('#st-body')).toContainText('Действующая версия справочников');
  for (const id of ['groups', 'calendar', 'shifts', 'docs', 'system', 'expert', 'overview']) {
    await view.locator(`[data-st=${id}]`).click();
    await expect(view.locator(`[data-st=${id}]`)).toHaveClass(/active/);
    await expect(view.locator('#st-body .page-head h2')).toBeVisible();
  }
  expect(errors).toEqual([]);
});

test('поиск по настройкам: открывается, фильтрует и переходит на экран', async ({ page }) => {
  const errors = watchErrors(page);
  await login(page, 'admin');
  await open(page, 'settings');
  const view = page.locator('#view-settings');
  await view.locator('#st-search').click();
  const modal = page.locator('#modal');
  await expect(modal.locator('#sp-q')).toBeFocused();
  await modal.locator('#sp-q').fill('групп');
  await expect(modal.locator('#sp-res button').first()).toBeVisible();
  await page.keyboard.press('Enter');
  await expect(view.locator('[data-st=groups]')).toHaveClass(/active/);
  expect(errors).toEqual([]);
});

test('календарь правил: выбор дня показывает панель дня', async ({ page }) => {
  const errors = watchErrors(page);
  await login(page, 'admin');
  await open(page, 'settings');
  const view = page.locator('#view-settings');
  await view.locator('[data-st=calendar]').click();
  await expect(view.locator('#cl-day')).toContainText('День не выбран');
  await view.locator('td[data-day]').nth(9).click();
  await expect(view.locator('#cl-day')).toContainText('День ');
  await expect(view.locator('td.sel')).toHaveCount(1);
  expect(errors).toEqual([]);
});
