/* «Сотрудники», «Права доступа», «Журнал аудита», справочники и документы в Настройках (шаг 6ж-3). */
import { expect, test } from '@playwright/test';
import { login, watchErrors } from './helpers.mjs';

const open = (page, view) => page.evaluate(v => window.navigate(v), view);

test('«Сотрудники»: список, карточка, редактор с контактами близких', async ({ page }) => {
  const errors = watchErrors(page);
  await login(page, 'admin');
  await open(page, 'employees');
  const view = page.locator('#view-employees');
  const rows = view.locator('tbody tr[data-card]');
  await expect(rows.first()).toBeVisible();
  expect(await rows.count()).toBeGreaterThan(3);
  await rows.first().click();
  const modal = page.locator('#modal');
  await expect(modal).toContainText('Табельный номер');
  await modal.locator('[data-edit]').click();
  await expect(modal.locator('#e-full')).toBeVisible();
  const before = await modal.locator('.contact-row').count();
  await modal.locator('#e-add-contact').click();
  await expect(modal.locator('.contact-row')).toHaveCount(before + 1);
  await modal.locator('.contact-row').last().locator('.c-name').fill('Тестовый Контакт');
  await modal.locator('.contact-row').last().locator('.c-del').click();
  await expect(modal.locator('.contact-row')).toHaveCount(before);
  await modal.locator('[data-cancel]').click();
  expect(errors).toEqual([]);
});

test('«Права доступа»: вкладки, матрица прав роли', async ({ page }) => {
  const errors = watchErrors(page);
  await login(page, 'admin');
  await open(page, 'access');
  const view = page.locator('#view-access');
  await expect(view.locator('#ac-body')).toContainText('Новая роль');
  await view.locator('[data-role]').first().click();
  const modal = page.locator('#modal');
  await expect(modal.locator('select[data-perm]').first()).toBeVisible();
  await modal.locator('[data-cancel]').click();
  await view.locator('[data-t=groups]').click();
  await expect(view.locator('#ag-add')).toBeVisible();
  await view.locator('[data-t=users]').click();
  await expect(view.locator('#au-q')).toBeVisible();
  await view.locator('#au-q').fill('admin');
  expect(await view.locator('tr[data-n]:visible').count()).toBeGreaterThan(0);
  expect(errors).toEqual([]);
});

test('«Журнал аудита»: таблица, фильтр, страницы', async ({ page }) => {
  const errors = watchErrors(page);
  await login(page, 'admin');
  await open(page, 'audit');
  const view = page.locator('#view-audit');
  await expect(view.locator('#au-body table')).toBeVisible();
  await view.locator('#af-q').fill('zzzz-нет-такого');
  await view.locator('#af-go').click();
  await expect(view.locator('#au-body')).toContainText('Записей нет');
  expect(errors).toEqual([]);
});

test('Настройки → «Документы»: департаменты, виды заявлений, двойные дни', async ({ page }) => {
  const errors = watchErrors(page);
  await login(page, 'admin');
  await open(page, 'settings');
  const view = page.locator('#view-settings');
  await view.locator('[data-st=docs]').click();
  await expect(view.locator('#dicts-body')).toContainText('Департаменты');
  await view.locator('#d-add-kind').click();
  const modal = page.locator('#modal');
  await expect(modal.locator('#k-code')).toBeVisible();
  await modal.locator('[data-cancel]').click();
  await view.locator('[data-st=calendar]').click();
  await expect(view.locator('#dp-body')).toContainText('ВИП-гости');
  await view.locator('[data-st=shifts]').click();
  await view.locator('#sh-add').click();
  await expect(modal.locator('#sh-code')).toBeVisible();
  await modal.locator('[data-cancel]').click();
  expect(errors).toEqual([]);
});
