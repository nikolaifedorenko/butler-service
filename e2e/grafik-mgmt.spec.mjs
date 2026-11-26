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

test('общая причина показана возле месяца, переход открывает указанный период', async ({ page }) => {
  await login(page, 'admin');
  await page.evaluate(() => window.navigate('mgmt'));
  const view = page.locator('#view-mgmt');
  const status = view.locator('.page-head').getByRole('status');
  await expect(status).toContainText(/Не закрыт предыдущий период.*\d{2}\.\d{2}\.\d{4}/s);
  const target = status.getByRole('button', { name: 'Открыть предыдущий период' });
  const next = page.waitForResponse(response => response.url().includes('/api/mgmt?') && response.ok());
  await target.click();
  const data = await (await next).json();
  await expect(view.locator('#ut-label')).toBeFocused();
  await expect(view.locator('#ut-label')).toContainText(String(data.year));
  await expect(view.locator('#ut-body table')).toBeVisible();
});

test('при чтении табеля подсказка объясняет, к кому обратиться, а ошибки расчёта остаются в строках', async ({ page }) => {
  await login(page, 'admin');
  await page.route('**/api/mgmt?*', async route => {
    const response = await route.fetch();
    const data = await response.json();
    const rows = [...data.rows];
    rows[0] = { ...rows[0], error_code: 'CHECK', error: 'Исправьте смену сотрудника' };
    await route.fulfill({ response, json: { ...data, can_close: false, rows } });
  });
  await page.evaluate(() => window.navigate('mgmt'));
  const view = page.locator('#view-mgmt');
  const status = view.locator('.page-head').getByRole('status');
  await expect(status).toContainText('Обратитесь к руководителю');
  await expect(status.getByRole('button')).toHaveCount(0);
  await expect(view.locator('#ut-body tbody')).toContainText('Исправьте смену сотрудника');
});

test('стрелка назад от полного месяца открывает вторую половину соседнего периода', async ({ page }) => {
  await login(page, 'admin');
  const data = await (await page.request.get('/api/mgmt?year=2026&month=11')).json();
  await page.route('**/api/mgmt?*', route => {
    const { searchParams } = new URL(route.request().url());
    const month = Number(searchParams.get('month'));
    if (month !== 10) return route.fulfill({ json: { ...data, year: 2026, month: 11, granularity: 'month' } });
    const half = searchParams.get('half') === '2' ? 2 : 1;
    return route.fulfill({ json: { ...data, year: 2026, month: 10, granularity: 'half_month', half,
      period: { start: half === 2 ? '2026-10-16' : '2026-10-01', end: half === 2 ? '2026-10-31' : '2026-10-15' } } });
  });
  await page.evaluate(() => { Object.assign(window.state, { year: 2026, month: 11 }); window.navigate('mgmt'); });
  const view = page.locator('#view-mgmt');
  await expect(view.locator('#ut-body table')).toBeVisible();
  await view.locator('#ut-prev').click();
  await expect(view.locator('#ut-label')).toContainText('16–31');
});
