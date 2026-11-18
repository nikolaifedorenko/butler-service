/* «Шахматка», «Блоки», «OOO» и «Мои гости» (шаг 6д-3). */
import { expect, test } from '@playwright/test';
import { login, watchErrors } from './helpers.mjs';

const open = (page, view) => page.evaluate(v => window.navigate(v), view);

test('«Блоки»: список, новая карточка с сеткой и закрытие', async ({ page }) => {
  const errors = watchErrors(page);
  await login(page, 'admin');
  await open(page, 'stays');
  const view = page.locator('#view-stays');
  await view.locator('[data-stab=blocks]').click();
  await expect(view.locator('#bl-total')).toContainText('Найдено блоков');
  await view.locator('#bl-short').check();
  await expect(view.locator('#bl-short')).toBeChecked();
  await view.locator('#bl-short').uncheck();
  await view.locator('#bl-new').click();
  const modal = page.locator('#modal');
  await expect(modal.locator('.bg-table')).toBeVisible();
  const cell = modal.locator('td[data-bg-c]').first();
  await cell.click();
  await expect(cell).toHaveClass(/sel/);
  await modal.locator('#bg-qty').fill('2');
  await modal.locator('#bg-set').click();
  await expect(cell).toHaveClass(/dirty/);
  await modal.locator('[data-close]').click();
  await expect(modal.locator('.bg-table')).toHaveCount(0);
  expect(errors).toEqual([]);
});

test('«OOO»: список, поиск без потери фокуса, форма', async ({ page }) => {
  const errors = watchErrors(page);
  await login(page, 'admin');
  await open(page, 'stays');
  const view = page.locator('#view-stays');
  await view.locator('[data-stab=ooo]').click();
  await expect(view.locator('#oo-total')).toContainText('Найдено OOO');
  const q = view.locator('#oo-q');
  await q.click();
  await page.keyboard.type('рем', { delay: 80 });
  await page.waitForTimeout(900);
  await expect(q).toBeFocused();
  await expect(q).toHaveValue('рем');
  await view.locator('#oo-new').click();
  const modal = page.locator('#modal');
  await expect(modal.locator('#hf-unit')).toBeVisible();
  await modal.locator('[data-close]').click();
  expect(errors).toEqual([]);
});

test('«Мои гости» у батлера: вкладки и поиск', async ({ page }) => {
  const errors = watchErrors(page);
  await login(page, 'ivanov');
  await open(page, 'mystays');
  const view = page.locator('#view-mystays');
  await expect(view.locator('.mine-date')).toBeVisible();
  await view.locator('[data-mtab=month]').click();
  await expect(view.locator('.mm-grid')).toBeVisible();
  await view.locator('[data-mtab=guests]').click();
  await expect(view.locator('#mg-total')).toContainText('Гостей');
  const q = view.locator('#mg-q');
  await q.click();
  await page.keyboard.type('а', { delay: 60 });
  await page.waitForTimeout(700);
  await expect(q).toBeFocused();
  expect(errors).toEqual([]);
});
