/* Журнал отметок и «Управленческий Табель» (шаг 6г-1): разделы на lit-html и настоящих модулях. */
import { expect, test } from '@playwright/test';
import { login, watchErrors } from './helpers.mjs';

test('журнал отметок: таблица месяца, фильтр по сотруднику, окно «Отметка за сотрудника»', async ({ page }) => {
  const errors = watchErrors(page);
  await login(page, 'admin');
  await page.evaluate(() => window.navigate('marks'));
  const journal = page.locator('#mk-journal');
  await expect(journal.locator('.panel-title')).toHaveText('Журнал отметок');
  await expect(journal.locator('#pj-body')).not.toContainText('Загрузка…');
  const rows = await journal.locator('#pj-body tbody tr').count();
  expect(rows).toBeGreaterThan(0);
  // фильтр по сотруднику сужает список
  const options = await journal.locator('#pj-emp option').count();
  expect(options).toBeGreaterThan(1);
  await journal.locator('#pj-emp').selectOption({ index: 1 });
  await expect(journal.locator('#pj-body')).not.toContainText('Загрузка…');
  expect(await journal.locator('#pj-body tbody tr').count()).toBeLessThanOrEqual(rows);
  // окно отметки за сотрудника
  await journal.locator('#pj-add').click();
  await expect(page.locator('#modal .modal-head h3')).toHaveText('Отметка за сотрудника');
  await expect(page.locator('#modal #pf-emp option').first()).toBeAttached();
  await page.locator('#modal [data-cancel]').click();
  await expect(page.locator('#modal-backdrop')).toHaveClass(/hidden/);
  // обновление доски не стирает журнал
  await page.locator('#mk-refresh').click();
  await expect(journal.locator('.panel-title')).toHaveText('Журнал отметок');
  expect(errors).toEqual([]);
});

test('Управленческий Табель: таблица, период, закрытие «всё или ничего» с перечнем проблем', async ({ page }) => {
  const errors = watchErrors(page);
  await login(page, 'admin');
  await page.evaluate(() => window.navigate('mgmt'));
  const view = page.locator('#view-mgmt');
  await expect(view.locator('#ut-body table')).toBeVisible();
  await expect(view.locator('#ut-body')).not.toContainText('Загрузка…');
  const label = (await view.locator('#ut-label').textContent()).trim();
  expect(label).toMatch(/\d{4}/);
  // на свежей базе предыдущий период не закрыт: у каждого сотрудника причина вместо расчёта
  await expect(view.locator('#ut-body tbody .badge.danger').first()).toHaveText('ошибка');
  await expect(view.locator('#ut-close')).toBeVisible();
  // подтверждение показывается и отменяется, ничего не закрывая
  await view.locator('#ut-close').click();
  await expect(page.locator('#modal .modal-head h3')).toHaveText('Закрыть период у всех?');
  await page.locator('#modal [data-no]').click();
  await expect(page.locator('#modal-backdrop')).toHaveClass(/hidden/);
  // подтверждение закрытия: сервер проверяет всех и возвращает перечень — период не закрывается ни у кого
  await view.locator('#ut-close').click();
  await page.locator('#modal [data-yes]').click();
  await expect(page.locator('#modal .modal-head h3')).toHaveText('Период не закрыт ни у кого');
  expect(await page.locator('#modal tbody tr[data-emp]').count()).toBeGreaterThan(0);
  await page.locator('#modal [data-cancel]').click();
  await expect(page.locator('#modal-backdrop')).toHaveClass(/hidden/);
  // листание периода меняет подпись и перерисовывает таблицу
  await view.locator('#ut-prev').click();
  await expect(view.locator('#ut-label')).not.toHaveText(label);
  await expect(view.locator('#ut-body table')).toBeVisible();
  expect(errors).toEqual([]);
});

test('Управленческий Табель: стирание раздела снаружи не ломает следующую загрузку', async ({ page }) => {
  const errors = watchErrors(page);
  await login(page, 'admin');
  await page.evaluate(() => window.navigate('mgmt'));
  await expect(page.locator('#view-mgmt #ut-body table')).toBeVisible();
  await page.evaluate(() => document.querySelectorAll('.view, .layer-pane').forEach(v => { v.innerHTML = ''; }));
  await page.evaluate(() => window.navigate('mgmt'));
  await expect(page.locator('#view-mgmt #ut-body table')).toBeVisible();
  expect(errors).toEqual([]);
});
