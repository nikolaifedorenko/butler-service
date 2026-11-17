/* «Мои отметки» и «Отметки» (шаг 6в-2): разделы на lit-html и настоящих модулях. */
import { expect, test } from '@playwright/test';
import { login, watchErrors } from './helpers.mjs';

async function open(page, view) {
  await page.evaluate(v => window.navigate(v), view);
  await expect(page.locator(`#view-${view}.active`)).toBeVisible();
}

test('каждый модуль выполняется один раз и без ?v= (иначе у него два экземпляра состояния)', async ({ page }) => {
  await login(page, 'gromova');
  const urls = await page.evaluate(() => performance.getEntriesByType('resource')
    .map(r => new URL(r.name).pathname + new URL(r.name).search).filter(u => u.startsWith('/static/js/')));
  expect(urls.filter(u => u.includes('?v=')).sort()).toEqual(['/static/js/ui/theme.js?v=' + urls.find(u => u.includes('theme.js')).split('?v=')[1]]);
  for (const f of ['core.js', 'app.js', 'modules/me.js', 'modules/marks.js', 'ui/html.js']) {
    expect(urls.filter(u => u === `/static/js/${f}`), f).toHaveLength(1);
  }
});

test('Мои отметки: смена, кнопка, статистика, история без «Загрузка…»', async ({ page }) => {
  const errors = watchErrors(page);
  await login(page, 'gromova');
  await open(page, 'me');
  const view = page.locator('#view-me');
  await expect(view.locator('.me-shift .title')).toHaveText(/\d\d:\d\d–\d\d:\d\d|смены нет/);
  await expect(view.locator('#punch-btn')).toBeVisible();
  await expect(view.locator('.me-stat')).toHaveCount(2);
  await expect(view.locator('#me-history .history-item').first()).toBeVisible();
  await expect(view.locator('#me-history')).not.toContainText('Загрузка…');
  await expect(view.locator('#car-strip')).not.toContainText('Загрузка…');
  await expect(view.locator('#car-strip .panel-title')).toHaveText('Электрокар');
  expect(errors).toEqual([]);
});

test('Мои отметки: приход и уход переключают кнопку и пополняют историю', async ({ page }) => {
  const errors = watchErrors(page);
  await login(page, 'ivanov');
  await open(page, 'me');
  const btn = page.locator('#view-me #punch-btn');
  await expect(btn).toBeVisible();
  const wasOn = (await btn.textContent()).includes('Ушёл');
  const before = await page.locator('#me-history .history-item').count();
  await btn.click();
  await expect(page.locator('#view-me #punch-btn')).toContainText(wasOn ? 'Пришёл' : 'Ушёл');
  await expect(page.locator('#me-history .history-item')).toHaveCount(Math.min(before + 1, 30));
  if (wasOn) {                                    // после «Ушёл» открывается окно описания переработки
    await expect(page.locator('#modal .modal-head h3')).toHaveText('Описание переработки');
    await page.locator('#modal [data-skip]').click();
    await expect(page.locator('#modal-backdrop')).toHaveClass(/hidden/);
  }
  expect(errors).toEqual([]);
});

test('Отметки: счётчики, карточки и обновление', async ({ page }) => {
  const errors = watchErrors(page);
  await login(page, 'admin');
  await open(page, 'marks');
  const view = page.locator('#view-marks');
  await expect(view.locator('.stat')).toHaveCount(3);
  await expect(view.locator('#mk-now')).toContainText('Сейчас');
  await expect(view.locator('#mk-body')).not.toContainText('Загрузка…');
  await expect(view.locator('#mk-body .panel-title').first()).toContainText('На работе прямо сейчас');
  const before = await view.locator('#mk-body .stat').count();
  const requests = [];
  page.on('request', r => { if (r.url().includes('/api/presence/board')) requests.push(r.url()); });
  await view.locator('#mk-refresh').click();
  await expect.poll(() => requests.length).toBe(1);
  await expect(view.locator('#mk-body .stat')).toHaveCount(before);   // перерисовка, а не дубль разметки
  expect(errors).toEqual([]);
});

test('окно: openModal принимает строки с разметкой и закрывается, не оставляя узлов', async ({ page }) => {
  await login(page, 'gromova');
  await open(page, 'me');
  await page.evaluate(() => window.openModal({ title: 'Проба <b>', subtitle: 'под <i>', body: '<p id="x">старый</p>', footer: '<button id="y">ok</button>' }));
  await expect(page.locator('#modal .modal-head h3')).toHaveText('Проба <b>');
  await expect(page.locator('#modal #x')).toHaveText('старый');
  await page.locator('#modal .x').click();
  await expect(page.locator('#modal-backdrop')).toHaveClass(/hidden/);
  expect(await page.locator('#modal').evaluate(el => el.children.length)).toBe(0);
});
