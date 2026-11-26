/* Обёртка «График» (шаг 6г-4): панель слоёв, переключение, права. */
import { expect, test } from '@playwright/test';
import { login, watchErrors } from './helpers.mjs';

const open = (page, view) => page.evaluate(v => window.navigate(v), view);
const tabs = page => page.locator('#grafik-tabs .layer-tab');

test('панель слоёв: четыре слоя админу, переключение показывает нужную панель', async ({ page }) => {
  const errors = watchErrors(page);
  await login(page, 'admin');
  await page.locator('#sidenav .nav-item[data-view=grafik]').click();
  await expect(page.locator('#view-grafik.active')).toBeVisible();
  await expect(tabs(page)).toHaveCount(4);
  expect(await tabs(page).evaluateAll(els => els.map(e => e.dataset.layer))).toEqual(['timesheet', 'schedule', 'fact', 'mgmt']);
  // слой по умолчанию — План / График
  await expect(page.locator('#grafik-tabs .layer-tab.active')).toHaveAttribute('data-layer', 'schedule');
  await expect(page.locator('#view-schedule.layer-pane.on table.sched')).toBeVisible();
  for (const [layer, marker] of [['timesheet', 'table.v4-grid'], ['fact', '#fm-body .fg-wrap'], ['mgmt', '#ut-body table']]) {
    await page.locator(`#grafik-tabs .layer-tab[data-layer=${layer}]`).click();
    await expect(page.locator('#grafik-tabs .layer-tab.active')).toHaveAttribute('data-layer', layer);
    await expect(page.locator(`#view-${layer}.layer-pane.on ${marker}`)).toBeVisible();
    await expect(page.locator('#view-grafik .layer-pane.on')).toHaveCount(1);
  }
  expect(errors).toEqual([]);
});

test('старые имена разделов открывают «График» на своём слое', async ({ page }) => {
  const errors = watchErrors(page);
  await login(page, 'admin');
  for (const layer of ['mgmt', 'fact', 'timesheet', 'schedule']) {
    await open(page, layer);
    await expect(page.locator('#view-grafik.active')).toBeVisible();
    await expect(page.locator('#grafik-tabs .layer-tab.active')).toHaveAttribute('data-layer', layer);
    await expect(page.locator(`#view-${layer}.layer-pane.on`)).toBeVisible();
  }
  expect(errors).toEqual([]);
});

test('сотрудник видит только слои по своим правам', async ({ page }) => {
  const errors = watchErrors(page);
  await login(page, 'ivanov');
  await open(page, 'grafik');
  await expect(tabs(page).first()).toBeVisible();
  const layers = await tabs(page).evaluateAll(els => els.map(e => e.dataset.layer));
  expect(layers).not.toContain('timesheet');
  expect(layers).not.toContain('mgmt');
  expect(layers).toContain('schedule');
  expect(errors).toEqual([]);
});

test('без прав на слои — сообщение, а не пустой экран', async ({ page }) => {
  const errors = watchErrors(page);
  await login(page, 'rukovod');
  await open(page, 'grafik');
  await expect(page.locator('#view-grafik .layer-noperm')).toContainText('Нет доступа к разделу «График»');
  await expect(tabs(page)).toHaveCount(0);
  expect(errors).toEqual([]);
});

test('стирание раздела снаружи: обёртка и слой рисуются заново', async ({ page }) => {
  const errors = watchErrors(page);
  await login(page, 'admin');
  await open(page, 'fact');
  await expect(page.locator('#view-fact #fm-body .fg-wrap')).toBeVisible();
  await page.evaluate(() => document.querySelectorAll('.view').forEach(v => { v.innerHTML = ''; }));
  await open(page, 'fact');
  await expect(tabs(page)).toHaveCount(4);
  await expect(page.locator('#view-fact #fm-body .fg-wrap')).toBeVisible();
  expect(errors).toEqual([]);
});
