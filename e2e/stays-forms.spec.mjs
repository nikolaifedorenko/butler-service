/* «Шахматка», формы и «Гости» (шаг 6д-2): форма брони с предпросмотром, справочник гостей, карточка и семейное дерево. */
import { expect, test } from '@playwright/test';
import { login, watchErrors } from './helpers.mjs';

const open = (page, view) => page.evaluate(v => window.navigate(v), view);

test('вкладка «Гости»: список, поиск без потери фокуса, карточка гостя с деревом', async ({ page }) => {
  const errors = watchErrors(page);
  await login(page, 'admin');
  await open(page, 'stays');
  const view = page.locator('#view-stays');
  await view.locator('[data-stab=guests]').click();
  await expect(view.locator('#gl-total')).toContainText('Найдено гостей');
  const rows = view.locator('[data-gl-row]');
  expect(await rows.count()).toBeGreaterThan(0);
  const q = view.locator('#gl-q');
  await q.click();
  await page.keyboard.type('а', { delay: 60 });
  await page.waitForTimeout(700);
  await expect(q).toBeFocused();
  await expect(q).toHaveValue('а');
  await q.fill('');
  await expect(view.locator('#gl-total')).toContainText('Найдено гостей');
  // карточка первого гостя и вкладка «Семья» (дерево рисуется шаблоном)
  await rows.first().click();
  const modal = page.locator('#modal');
  await expect(modal).toContainText('История проживаний');
  await expect(modal.locator('.ft-tree')).toBeVisible();
  await expect(modal.locator('[data-ft-person]').first()).toBeVisible();
  await modal.locator('[data-ft-add=spouse]').click();
  await expect(modal.locator('[data-ft-q]')).toBeVisible();
  await modal.locator('[data-ft-cancel]').click();
  await expect(modal.locator('[data-ft-q]')).toHaveCount(0);
  expect(errors).toEqual([]);
});

test('форма брони: открывается с кнопкой «Проверить» и закрывается без ошибок', async ({ page }) => {
  const errors = watchErrors(page);
  await login(page, 'admin');
  await open(page, 'stays');
  const view = page.locator('#view-stays');
  await expect(view.locator('.sb-grid')).toBeVisible();
  await view.locator('#sb-new').click();
  const modal = page.locator('#modal');
  await expect(modal.locator('#rf-preview')).toBeVisible();
  await expect(modal.locator('select').first()).toBeVisible();
  await modal.locator('[data-close]').click();
  await expect(modal.locator('#rf-preview')).toHaveCount(0);
  expect(errors).toEqual([]);
});
