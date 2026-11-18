/* «Табель» и «Факт» (шаг 6г-2): слои Графика на lit-html и настоящих модулях. */
import { expect, test } from '@playwright/test';
import { login, watchErrors } from './helpers.mjs';

async function open(page, view) {
  await page.evaluate(v => window.navigate(v), view);
}

test('Табель: сетка месяца, правка ячейки плашкой, окна «Заполнить» и «Сбросить», листание месяца', async ({ page }) => {
  const errors = watchErrors(page);
  await login(page, 'admin');
  await open(page, 'timesheet');
  const view = page.locator('#view-timesheet');
  await expect(view.locator('#tb-body table.v4-grid')).toBeVisible();
  await expect(view.locator('#tb-body')).not.toContainText('Загрузка…');
  expect(await view.locator('thead th.v4-day').count()).toBeGreaterThanOrEqual(28);
  await expect(view.locator('#tb-fill')).toBeVisible();
  // правка ячейки: плашки значений, выбор показывается в строке выбора
  const cell = view.locator('td.v4-cell.edit').first();
  await cell.click();
  await expect(page.locator('#modal .modal-head h3')).toContainText('Табель ·');
  const chips = page.locator('#modal .tc-chip[data-code]');
  expect(await chips.count()).toBeGreaterThan(2);
  await chips.nth(1).click();
  await expect(page.locator('#modal #tc-sel')).toContainText(/Выбрано|будет очищена/);
  await expect(page.locator('#modal .tc-chip.sel')).toHaveCount(1);
  await page.locator('#modal [data-cancel]').click();
  await expect(page.locator('#modal-backdrop')).toHaveClass(/hidden/);
  // «Заполнить из циклов» и «Сбросить» открываются и закрываются
  await view.locator('#tb-fill').click();
  await expect(page.locator('#modal .modal-head h3')).toHaveText('Заполнить Табель из циклов');
  await expect(page.locator('#modal #tf-mode option')).toHaveCount(2);
  await page.locator('#modal [data-cancel]').click();
  await view.locator('#tb-reset').click();
  await expect(page.locator('#modal .modal-head h3')).toHaveText('Сбросить Табель');
  expect(await page.locator('#modal #tr-emp option').count()).toBeGreaterThan(1);
  await page.locator('#modal [data-cancel]').click();
  // листание месяца
  const label = (await view.locator('#tb-label').textContent()).trim();
  await view.locator('#tb-next').click();
  await expect(view.locator('#tb-label')).not.toHaveText(label);
  await expect(view.locator('#tb-body table.v4-grid')).toBeVisible();
  expect(errors).toEqual([]);
});

test('Факт: гант месяца, день, сотрудник; переключение вкладок и листание', async ({ page }) => {
  const errors = watchErrors(page);
  await login(page, 'admin');
  await open(page, 'fact');
  const view = page.locator('#view-fact');
  await expect(view.locator('#fc-mode button.active')).toHaveText('Месяц');
  await expect(view.locator('#fm-body')).not.toContainText('Загрузка…');
  await expect(view.locator('#fm-body .fg-wrap svg')).toBeVisible();
  expect(await view.locator('#fm-body .fg-names .fg-row').count()).toBeGreaterThan(0);
  await expect(view.locator('#fm-meta')).toContainText('округление до шага');
  expect(await view.locator('#fm-body svg rect.fg-cat').count()).toBeGreaterThan(0);
  await view.locator('#fm-next').click();
  await expect(view.locator('#fm-body .fg-wrap svg')).toBeVisible();
  // «День»
  await view.locator('#fc-mode button[data-mode=numbers]').click();
  await expect(view.locator('#fc-mode button.active')).toHaveText('День');
  await expect(view.locator('#fd-body table.data')).toBeVisible();
  const day = (await view.locator('#fd-label').textContent()).trim();
  await view.locator('#fd-prev').click();
  await expect(view.locator('#fd-label')).not.toHaveText(day);
  await expect(view.locator('#fd-body table.data')).toBeVisible();
  await expect(view.locator('#fd-meta')).toContainText('Шаг округления');
  // «Сотрудник»
  await view.locator('#fc-mode button[data-mode=sessions]').click();
  await expect(view.locator('#fc-emp')).toBeVisible();
  expect(await view.locator('#fc-emp option').count()).toBeGreaterThan(0);
  await view.locator('#fc-go').click();
  await expect(view.locator('#fc-body')).not.toContainText('Загрузка…');
  await expect(view.locator('#fc-body .panel-title, #fc-body .empty').first()).toBeVisible();
  expect(errors).toEqual([]);
});

test('Табель и Факт: стирание раздела снаружи не ломает следующую загрузку', async ({ page }) => {
  const errors = watchErrors(page);
  await login(page, 'admin');
  await open(page, 'timesheet');
  await expect(page.locator('#view-timesheet #tb-body table.v4-grid')).toBeVisible();
  await page.evaluate(() => document.querySelectorAll('.view, .layer-pane').forEach(v => { v.innerHTML = ''; }));
  await open(page, 'timesheet');
  await expect(page.locator('#view-timesheet #tb-body table.v4-grid')).toBeVisible();
  await open(page, 'fact');
  await expect(page.locator('#view-fact #fm-body .fg-wrap svg')).toBeVisible();
  await page.evaluate(() => document.querySelectorAll('.view, .layer-pane').forEach(v => { v.innerHTML = ''; }));
  await open(page, 'fact');
  await expect(page.locator('#view-fact #fm-body .fg-wrap svg')).toBeVisible();
  expect(errors).toEqual([]);
});
