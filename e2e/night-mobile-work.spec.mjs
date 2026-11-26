import { expect, test } from '@playwright/test';
import { login } from './helpers.mjs';

test.use({ viewport: { width: 390, height: 844 } });

async function nightFixture(page) {
  await login(page, 'admin');
  const { reports } = await (await page.request.get('/api/night/reports')).json();
  const { id } = reports.find(report => report.status === 'closed');
  const { report } = await (await page.request.get(`/api/night/reports/${id}`)).json();
  return report;
}

/* Seed an open shift from the real report schema so these browser tests can run by day or night. */
async function openShift(page, report, area, owner) {
  const zone = report.zones.find(z => z.zone_id === area.zone_id);
  Object.assign(report, { status: 'open', readonly: false, closed_at: null, close_reason: '',
    result: '', result_title: '—' });
  Object.assign(area, { status: 'taken', status_title: 'в работе', taken_by: owner,
    taken_by_name: 'Дежурный', taken_at: report.deadline });
  report.progress.free -= 1;
  report.progress.taken += 1;
  zone.free -= 1;
  zone.taken += 1;
  await page.route('**/api/night/today', route => route.fulfill({ json: { available: true, report } }));
}

async function openNight(page) {
  await page.evaluate(() => window.navigate('night'));
  const view = page.locator('#view-night');
  await expect(view.locator('[data-zone-open]').first()).toBeVisible();
  return view;
}

async function resumeFixture(page) {
  const report = await nightFixture(page);
  const { user } = await (await page.request.get('/api/auth/me')).json();
  const area = report.areas.find(a => a.zone_id && a.status === 'free' && a.items.length);
  await openShift(page, report, area, user.id);
  const takeRequests = [];
  await page.route(`**/api/night/sections/${area.id}/take`, route => {
    takeRequests.push(route.request().method());
    return route.fulfill({ json: { ok: true, section: area, already: true, warning: null } });
  });
  const view = await openNight(page);
  const resume = view.getByRole('button', { name: 'Продолжить обход' });
  await expect(resume).toBeInViewport();
  return { report, area, view, resume, takeRequests };
}

test('телефон открывает свой чек-лист в его зоне без повторного взятия в работу', async ({ page }) => {
  const { area, view, resume, takeRequests } = await resumeFixture(page);
  expect((await resume.boundingBox()).y).toBeLessThan((await view.locator('[data-zone-open]').first().boundingBox()).y);
  await resume.click();
  await expect(view.locator('.night-area')).toContainText(area.items[0].text);
  expect(takeRequests).toEqual([]);
  await expect(view.locator('[data-crumb=zone]')).toHaveText(area.zone_name);
  await view.locator('[data-crumb=zone]').click();
  await expect(view.locator('.night-object').filter({ hasText: area.name }).first()).toBeVisible();
});

for (const staleState of ['object-completed', 'other-owner', 'shift-closed']) {
  test(`продолжение обхода сверяет последнее состояние смены (${staleState})`, async ({ page }) => {
    const { report, area, view, resume, takeRequests } = await resumeFixture(page);
    if (staleState === 'object-completed') Object.assign(area, { status: 'done', status_title: 'закрыта' });
    if (staleState === 'other-owner') area.taken_by += 1;
    if (staleState === 'shift-closed') Object.assign(report, { status: 'closed', readonly: true, result_title: 'неполный' });
    const refreshed = page.waitForResponse('**/api/night/today', { timeout: 8000 });
    await resume.click();
    await refreshed;
    await expect(resume).toBeHidden();
    await expect(view.locator('[data-zone-open]').first()).toBeVisible();
    await expect(view.locator('.night-area')).toHaveCount(0);
    expect(takeRequests).toEqual([]);
    if (staleState === 'shift-closed') await expect(view.locator('.ro-banner')).toContainText('итог: неполный');
  });
}

test('на телефоне чужой обход не предлагается, первая зона предшествует сводке и электрокарам', async ({ page }) => {
  const report = await nightFixture(page);
  const { user } = await (await page.request.get('/api/auth/me')).json();
  const area = report.areas.find(a => a.zone_id && a.status === 'free');
  await openShift(page, report, area, user.id + 1);

  const view = await openNight(page);
  await expect(view.getByRole('button', { name: 'Продолжить обход' })).toHaveCount(0);
  const zone = view.locator('[data-zone-open]').first();
  await expect(zone).toBeInViewport();
  const summary = view.locator('.stat-grid');
  expect((await zone.boundingBox()).y).toBeLessThan((await summary.boundingBox()).y);
  expect((await summary.boundingBox()).height).toBeLessThan(200);
  expect((await summary.boundingBox()).y).toBeLessThan((await view.locator('#night-cars-open').boundingBox()).y);
});

test('проверка электрокаров доступна с телефона в «Действиях»', async ({ page }) => {
  const report = await nightFixture(page);
  const area = report.areas.find(a => a.zone_id && a.status === 'free');
  await openShift(page, report, area, null);
  const view = await openNight(page);
  await view.getByRole('button', { name: 'Действия', exact: true }).click();
  const checkCars = view.locator('#night-head-actions').getByRole('button', { name: 'Проверить электрокары' });
  await expect(checkCars).toBeInViewport();
  await checkCars.click();
  await expect(page.getByRole('heading', { name: 'Проверка электрокаров' })).toBeVisible();
});

test('закрытая смена показывает итог первой, архив и выгрузки доступны по кнопке «Действия»', async ({ page }) => {
  const report = await nightFixture(page);
  await page.route('**/api/night/today', route => route.fulfill({ json: { available: true, report } }));
  const view = await openNight(page);
  const result = view.locator('.ro-banner');
  await expect(result).toContainText(`итог: ${report.result_title}`);
  await expect(result).toBeInViewport();
  expect((await result.boundingBox()).y).toBeLessThan((await view.locator('[data-zone-open]').first().boundingBox()).y);
  await expect(view.getByRole('button', { name: 'Продолжить обход' })).toHaveCount(0);

  await view.locator('[data-zone-open]').first().click();
  await expect(view.locator('#night-obj-q')).toBeVisible();
  const actions = view.getByRole('button', { name: 'Действия', exact: true });
  await expect(actions).toHaveAttribute('aria-expanded', 'false');
  await expect(view.getByRole('button', { name: 'Архив' })).toBeHidden();
  await actions.press('Enter');
  await expect(actions).toHaveAttribute('aria-expanded', 'true');
  await expect(view.getByRole('button', { name: 'DOCX' })).toBeVisible();
  await expect(view.getByRole('button', { name: 'PDF' })).toBeVisible();
  await view.getByRole('button', { name: 'Архив' }).click();
  await expect(page.getByRole('heading', { name: 'Архив ночных отчётов' })).toBeVisible();
  await page.locator(`#modal [data-open="${report.id}"]`).click();
  await expect(result).toContainText(`итог: ${report.result_title}`);
  await expect(view.getByRole('button', { name: 'Архив' })).toBeHidden();
  await actions.click();
  const toToday = view.getByRole('button', { name: 'К текущей смене' });
  await expect(toToday).toBeVisible();
  const docx = page.waitForEvent('download', { timeout: 8000 });
  await view.getByRole('button', { name: 'DOCX' }).click();
  expect((await docx).suggestedFilename()).toMatch(/\.docx$/);

  const pdfPath = `**/api/night/reports/${report.id}/export.pdf`;
  await page.route(pdfPath, route => route.fulfill({
    body: '%PDF-1.4',
    headers: { 'Content-Disposition': 'attachment; filename="night-test.pdf"', 'Content-Type': 'application/pdf' },
  }));
  const pdf = page.waitForEvent('download', { timeout: 8000 });
  await view.getByRole('button', { name: 'PDF' }).click();
  expect((await pdf).suggestedFilename()).toBe('night-test.pdf');

  await toToday.click();
  await expect(actions).toHaveAttribute('aria-expanded', 'false');
  await expect(toToday).toHaveCount(0);
});

test('запоздалый ответ текущей смены не заменяет открытый архив', async ({ page }) => {
  const report = await nightFixture(page);
  const area = report.areas.find(a => a.zone_id && a.status === 'free');
  await openShift(page, report, area, null);
  const view = await openNight(page);

  let release;
  const responseGate = new Promise(resolve => { release = resolve; });
  const todayPath = '**/api/night/today';
  await page.route(todayPath, async route => {
    await responseGate;
    await route.fulfill({ json: { available: true, report } });
  }, { times: 1 });

  const refresh = page.waitForRequest(todayPath, { timeout: 8000 });
  await page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')));
  await refresh;
  try {
    await view.getByRole('button', { name: 'Действия', exact: true }).click();
    await view.getByRole('button', { name: 'Архив' }).click();
    await page.locator(`#modal [data-open="${report.id}"]`).click();
    const result = view.locator('.ro-banner');
    await expect(result).toBeVisible();

    const delayed = page.waitForResponse(todayPath, { timeout: 8000 });
    release();
    await (await delayed).finished();
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    await expect(result).toBeVisible();
  } finally {
    release();
  }
});
