/* «План / График» (шаг 6г-3): сетка, редакторы ячейки и периода на lit-html и настоящих модулях. */
import { expect, test } from '@playwright/test';
import { login, watchErrors } from './helpers.mjs';

const open = (page, view) => page.evaluate(v => window.navigate(v), view);

test('График: сетка месяца, блоки, легенда, поиск и листание месяца', async ({ page }) => {
  const errors = watchErrors(page);
  await login(page, 'admin');
  await open(page, 'schedule');
  const view = page.locator('#view-schedule');
  await expect(view.locator('#grid-host table.sched')).toBeVisible();
  await expect(view.locator('#grid-host')).not.toContainText('Загрузка…');
  const all = await view.locator('tr.emp-row').count();
  expect(all).toBeGreaterThan(3);
  expect(await view.locator('tr.group-row').count()).toBeGreaterThan(0);
  expect(await view.locator('thead th.weekend').count()).toBeGreaterThan(0);
  expect(await view.locator('#grid-legend .chip').count()).toBeGreaterThan(3);
  await expect(view.locator('#m-label')).toContainText(/\d{4}/);
  // поиск по ФИО сужает список и возвращает обратно; поле не теряет фокус
  const name = (await view.locator('tr.emp-row .nm').first().textContent()).trim().split(' ')[0];
  await view.locator('#f-text').fill(name);
  await expect(view.locator('#f-text')).toBeFocused();
  expect(await view.locator('tr.emp-row').count()).toBeLessThan(all);
  await view.locator('#f-text').fill('');
  await expect(view.locator('tr.emp-row')).toHaveCount(all);
  // листание месяца
  const label = (await view.locator('#m-label').textContent()).trim();
  await view.locator('#m-next').click();
  await expect(view.locator('#m-label')).not.toHaveText(label);
  await expect(view.locator('#grid-host table.sched')).toBeVisible();
  expect(errors).toEqual([]);
});

test('График: окно ячейки (смены, отсутствие, переход в Табель) и окно «Выходной за часы»', async ({ page }) => {
  const errors = watchErrors(page);
  await login(page, 'admin');
  await open(page, 'schedule');
  const view = page.locator('#view-schedule');
  await expect(view.locator('#grid-host table.sched')).toBeVisible();
  await view.locator('.cellbtn:not([disabled]):not(.inactive):not(.empty)').first().click();
  const modal = page.locator('#modal');
  await expect(modal.locator('.status-line').first()).toContainText('Табель');
  await expect(modal.locator('#cell-tabel')).toBeVisible();
  await expect(modal.locator('#cell-sh-chips .tc-chip').first()).toBeVisible();   // плашки ручной смены
  await modal.locator('#cell-sh-chips .tc-chip.manual').click();
  await expect(modal.locator('#cell-sh-manual')).toBeVisible();
  await expect(modal.locator('#cell-abs-doc option').first()).toHaveText('— авто по точке ввода —');
  await modal.locator('[data-cancel]').click();
  await expect(page.locator('#modal-backdrop')).toHaveClass(/hidden/);
  // «Выходной за часы»
  await view.locator('#btn-range').click();
  await expect(modal.locator('.modal-head h3')).toHaveText('Выходной за часы');
  expect(await modal.locator('#rg-emps input[type=checkbox]').count()).toBeGreaterThan(3);
  await modal.locator('[data-ok]').click();                                        // без выбора — предупреждение, окно открыто
  await expect(page.locator('#toast-host')).toContainText('Отметьте сотрудников');
  await modal.locator('[data-cancel]').click();
  expect(errors).toEqual([]);
});

test('График: из окна ячейки — переход в Табель к выбранному дню', async ({ page }) => {
  const errors = watchErrors(page);
  await login(page, 'admin');
  await open(page, 'schedule');
  const view = page.locator('#view-schedule');
  await expect(view.locator('#grid-host table.sched')).toBeVisible();
  await view.locator('.cellbtn:not([disabled]):not(.inactive):not(.empty)').first().click();
  await page.locator('#modal #cell-tabel').click();
  await expect(page.locator('#modal .modal-head h3')).toContainText('Табель ·');   // открылось окно ячейки Табеля
  await page.locator('#modal [data-cancel]').click();
  expect(errors).toEqual([]);
});

test('Назначить отсутствие из Табеля: окно с кодами и сотрудниками', async ({ page }) => {
  const errors = watchErrors(page);
  await login(page, 'admin');
  await open(page, 'timesheet');
  await page.locator('#view-timesheet #tb-absence').click();
  const modal = page.locator('#modal');
  await expect(modal.locator('.modal-head h3')).toHaveText('Назначить отсутствие (код Табеля)');
  await expect(modal.locator('#rg-code option').first()).toBeAttached();
  await expect(modal.locator('#rg-code')).not.toContainText('загрузка');
  await modal.locator('[data-cancel]').click();
  expect(errors).toEqual([]);
});

test('График для сотрудника: только просмотр', async ({ page }) => {
  const errors = watchErrors(page);
  await login(page, 'ivanov');
  await open(page, 'schedule');
  const view = page.locator('#view-schedule');
  await expect(view.locator('#grid-host table.sched')).toBeVisible();
  await expect(view.locator('.ro-banner')).toBeVisible();
  await expect(view.locator('#grid-host')).toHaveClass(/ro/);
  await expect(view.locator('#btn-range')).toHaveCount(0);
  await view.locator('.cellbtn:not([disabled])').first().dispatchEvent('click');  // клики отключены: обработчика нет
  await expect(page.locator('#modal-backdrop')).toHaveClass(/hidden/);
  expect(errors).toEqual([]);
});

test('График: стирание раздела снаружи не ломает следующую загрузку', async ({ page }) => {
  const errors = watchErrors(page);
  await login(page, 'admin');
  await open(page, 'schedule');
  await expect(page.locator('#view-schedule table.sched')).toBeVisible();
  await page.evaluate(() => document.querySelectorAll('.view, .layer-pane').forEach(v => { v.innerHTML = ''; }));
  await open(page, 'schedule');
  await expect(page.locator('#view-schedule table.sched')).toBeVisible();
  expect(errors).toEqual([]);
});
