/* Экраны шахматки в Настройках: сопровождение, поля, метки, фонд и категории (шаг 6д-4). */
import { expect, test } from '@playwright/test';
import { login, watchErrors } from './helpers.mjs';

const open = (page, view) => page.evaluate(v => window.navigate(v), view);

async function openScreen(page, id) {
  await open(page, 'settings');
  const view = page.locator('#view-settings');
  await view.locator(`[data-st=${id}]`).click();
  return view;
}

test('«Сопровождение»: коды, нагрузка, дата правил', async ({ page }) => {
  const errors = watchErrors(page);
  await login(page, 'admin');
  const view = await openScreen(page, 'stays_escort');
  await expect(view.locator('#se-codes-table')).toBeVisible();
  await expect(view.locator('#se-special')).toBeVisible();
  await view.locator('#se-code-add').click();
  const modal = page.locator('#modal');
  await expect(modal.locator('#vc-code')).toBeVisible();
  await modal.locator('[data-close]').click();
  await expect(modal.locator('#vc-code')).toHaveCount(0);
  await view.locator('#se-date').fill('1990-01-01');
  await expect(view.locator('[data-rules-missing]')).toBeVisible();
  await view.locator('#se-date').fill(new Date().toISOString().slice(0, 10));
  await expect(view.locator('[data-rules-cats]')).toBeVisible();
  expect(errors).toEqual([]);
});

test('«Поля» и «Метки»: формы открываются и закрываются', async ({ page }) => {
  const errors = watchErrors(page);
  await login(page, 'admin');
  let view = await openScreen(page, 'stays_fields');
  await view.locator('#sfl-add').click();
  const modal = page.locator('#modal');
  await expect(modal.locator('#sfl-kind')).toBeVisible();
  await modal.locator('[data-close]').click();
  view = await openScreen(page, 'stays_labels');
  await view.locator('#slb-add').click();
  await expect(modal.locator('#slb-color')).toBeVisible();
  await modal.locator('[data-close]').click();
  expect(errors).toEqual([]);
});

test('«Фонд и категории»: дерево, вкладки, справочник флагов, окно загрузки', async ({ page }) => {
  const errors = watchErrors(page);
  await login(page, 'admin');
  const view = await openScreen(page, 'stays_fund');
  await expect(view.locator('[data-fund-node]').nth(5)).toBeVisible();
  await expect(view.locator('#fund-history [data-fund-ver]').first()).toBeVisible();
  for (const tab of ['flags', 'cats', 'kinds', 'units']) {
    await view.locator(`[data-fund-tab=${tab}]`).click();
    await expect(view.locator(`[data-fund-tab=${tab}]`)).toHaveClass(/btn-primary/);
  }
  await view.locator('[data-fund-node]').nth(1).click();
  await expect(view.locator('[data-fund-node]').nth(1)).toHaveClass(/active/);
  const modal = page.locator('#modal');
  await view.locator('#fund-flags-dict').click();
  await expect(modal).toContainText('Флаги объектов');
  await modal.locator('[data-close]').click();
  await view.locator('#fund-upload').click();
  await expect(modal.locator('#fu-mode')).toBeVisible();
  await modal.locator('#fu-mode').selectOption('reset');
  await expect(modal.locator('#fu-reset')).toBeVisible();
  await expect(modal.locator('#fu-go')).toHaveText('Проверить');
  await modal.locator('[data-close]').click();
  expect(errors).toEqual([]);
});
