/* «Ночной отчёт» и «Электрокары» (шаг 6е): уровни обхода, поиск, окна, история кара. */
import { expect, test } from '@playwright/test';
import { login, watchErrors } from './helpers.mjs';

const open = (page, view) => page.evaluate(v => window.navigate(v), view);

test('«Ночной отчёт»: зоны → объекты → чек-лист, поиск не теряет фокус, архив', async ({ page }) => {
  const errors = watchErrors(page);
  await login(page, 'admin');
  await open(page, 'night');
  const view = page.locator('#view-night');
  await expect(view.locator('#night-body')).not.toContainText('Загрузка…');
  await expect(view.locator('#night-archive')).toBeVisible();
  const zones = view.locator('[data-zone-open]');
  if (await zones.count()) {
    await zones.first().click();
    const q = view.locator('#night-obj-q');
    await expect(q).toBeVisible();
    await q.click();
    await page.keyboard.type('в', { delay: 60 });
    await expect(q).toBeFocused();
    await expect(q).toHaveValue('в');
    await q.fill('');
    await view.locator('[data-ofilter=all]').click();
    const first = view.locator('[data-sec-open]').first();
    if (await first.count()) {
      await first.click();
      await expect(view.locator('.night-area')).toBeVisible();
      await view.locator('[data-crumb=zones]').click();
      await expect(view.locator('[data-zone-open]').first()).toBeVisible();
    }
  }
  await view.locator('#night-archive').click();
  const modal = page.locator('#modal');
  await expect(modal).toContainText('Архив ночных отчётов');
  await modal.locator('[data-cancel]').click();
  expect(errors).toEqual([]);
});

test('«Электрокары»: список, фильтр, поиск и история кара', async ({ page }) => {
  const errors = watchErrors(page);
  await login(page, 'admin');
  await open(page, 'cars');
  const view = page.locator('#view-cars');
  await expect(view.locator('.stat-grid')).toBeVisible();
  const rows = view.locator('tbody tr');
  expect(await rows.count()).toBeGreaterThan(0);
  const q = view.locator('#cars-q');
  await q.click();
  await page.keyboard.type('zzzzz', { delay: 40 });
  await expect(q).toBeFocused();
  await expect(view.locator('tbody')).toContainText('Нет каров по фильтру');
  await q.fill('');
  await expect(rows.first()).not.toContainText('Нет каров по фильтру');
  await view.locator('[data-act=history]').first().click();
  const modal = page.locator('#modal');
  await expect(modal).toContainText('История кара');
  await modal.locator('[data-cancel]').click();
  expect(errors).toEqual([]);
});
