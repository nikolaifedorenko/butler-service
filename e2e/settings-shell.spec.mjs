/* «Настройки»: оболочка, переходы между экранами, поиск, черновик (шаг 6ж-1). */
import { expect, test } from '@playwright/test';
import { login, watchErrors } from './helpers.mjs';

const open = (page, view) => page.evaluate(v => window.navigate(v), view);

test('оболочка Настроек: навигация по экранам без ошибок и подсветка текущего', async ({ page }) => {
  const errors = watchErrors(page);
  await login(page, 'admin');
  await open(page, 'settings');
  const view = page.locator('#view-settings');
  await expect(view.locator('#st-body')).toContainText('Действующая версия справочников');
  for (const id of ['groups', 'calendar', 'shifts', 'docs', 'system', 'expert', 'overview']) {
    await view.locator(`[data-st=${id}]`).click();
    await expect(view.locator(`[data-st=${id}]`)).toHaveClass(/active/);
    await expect(view.locator('#st-body .page-head h2')).toBeVisible();
  }
  expect(errors).toEqual([]);
});

test('поиск по настройкам: открывается, фильтрует и переходит на экран', async ({ page }) => {
  const errors = watchErrors(page);
  await login(page, 'admin');
  await open(page, 'settings');
  const view = page.locator('#view-settings');
  const search = view.getByRole('button', { name: /Поиск по настройкам/ });
  await expect(search).not.toContainText(/(?:⌘|Cmd|Ctrl)\s*\+?\s*K/i);
  await search.click();
  const modal = page.locator('#modal');
  await expect(modal.locator('#sp-q')).toBeFocused();
  await modal.locator('#sp-q').fill('групп');
  await expect(modal.locator('#sp-res button').first()).toBeVisible();
  await page.keyboard.press('Enter');
  await expect(view.locator('[data-st=groups]')).toHaveClass(/active/);
  expect(errors).toEqual([]);
});

test('поиск настроек на телефоне открывает нужную вкладку и блок', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await login(page, 'admin');
  await open(page, 'settings');
  const search = page.getByRole('button', { name: 'Поиск по настройкам' });
  await expect(search.locator('span')).toBeVisible();

  await search.click();
  await page.locator('#sp-q').fill('чек-листы зон');
  await page.keyboard.press('Enter');
  await expect(page.locator('#st-body [data-dtab=items]')).toHaveClass(/active/);

  await search.click();
  await page.locator('#sp-q').fill('медиа');
  await page.keyboard.press('Enter');
  const media = page.getByRole('heading', { name: 'Медиа и хранение' });
  await expect(media).toBeFocused();
  await expect(media).toBeInViewport();
  await page.getByRole('button', { name: 'Открыть правила объекта' }).click();
  await expect(page.getByRole('heading', { name: 'Прочие правила объекта' })).toBeFocused();

  await search.click();
  await page.locator('#sp-q').fill('значение и окно');
  await page.keyboard.press('Enter');
  await expect(page.locator('#st-body [data-tab=windows]')).toHaveClass(/active/);
});

test('сохранение базового цикла не сбрасывает черновик групп', async ({ page }) => {
  await login(page, 'admin');
  await open(page, 'settings');
  await page.locator('[data-st=groups]').click();
  await page.locator('#g-new').fill('Проверка черновика');
  await page.locator('#g-add').click();
  const group = page.getByText('Проверка черновика', { exact: true });
  await expect(group).toBeVisible();
  await page.route('**/api/settings/base', route => route.fulfill({
    json: { base: route.request().postDataJSON() },
  }));
  await page.locator('#b-save').click();
  await expect(page.getByText('Базовый цикл сохранён и действует на все месяцы')).toBeVisible();
  await expect(page.locator('#g-new')).toBeVisible();
  await expect(group).toBeVisible();
  await expect(page.locator('[data-draft-publish]')).toBeEnabled();
});

test('правила объекта и реквизиты сохраняются в своих блоках', async ({ page }) => {
  await login(page, 'admin');
  await open(page, 'settings');
  await page.locator('[data-st=docs]').click();
  const docs = page.locator('#st-body');
  const rulesPanel = docs.locator('.panel').filter({ has: page.getByRole('heading', { name: 'Прочие правила объекта' }) });
  const company = docs.locator('#d-company');
  await company.fill('Несохранённые реквизиты');
  const rules = await page.request.get('/api/settings');
  const { rules: ruleValues } = await rules.json();
  await page.route('**/api/settings', route => route.request().method() === 'PUT'
    ? route.fulfill({ json: { rules: ruleValues } })
    : route.continue());
  await rulesPanel.getByRole('button', { name: 'Сохранить правила объекта' }).click({ timeout: 3000 });
  await expect(page.getByText('Правила объекта сохранены')).toBeVisible();
  await expect(company).toHaveValue('Несохранённые реквизиты');

  const photoLimit = rulesPanel.locator('[data-k=photo_max_mb]');
  await photoLimit.fill(String(ruleValues.photo_max_mb + 1));
  await page.route('**/api/settings/doc', route => route.fulfill({
    json: { doc: route.request().postDataJSON() },
  }));
  await docs.getByRole('button', { name: 'Сохранить реквизиты' }).click();
  await expect(page.getByText('Реквизиты сохранены')).toBeVisible();
  await expect(photoLimit).toHaveValue(String(ruleValues.photo_max_mb + 1));
});

test('календарь правил: выбор дня показывает панель дня', async ({ page }) => {
  const errors = watchErrors(page);
  await login(page, 'admin');
  await open(page, 'settings');
  const view = page.locator('#view-settings');
  await view.locator('[data-st=calendar]').click();
  await expect(view.locator('#cl-day')).toContainText('День не выбран');
  await view.locator('td[data-day]').nth(9).click();
  await expect(view.locator('#cl-day')).toContainText('День ');
  await expect(view.locator('td.sel')).toHaveCount(1);
  expect(errors).toEqual([]);
});

test('«Расчёт», «Коды», «Оплата», «Чаты и Почта», «Электрокары», «Ночной обход»: экраны открываются и отзываются (6ж-2)', async ({ page }) => {
  const errors = watchErrors(page);
  await login(page, 'admin');
  await open(page, 'settings');
  const view = page.locator('#view-settings');
  for (const id of ['calc', 'codes', 'pay', 'notify', 'cars', 'night']) {
    await view.locator(`[data-st=${id}]`).click();
    await expect(view.locator(`[data-st=${id}]`)).toHaveClass(/active/);
    await expect(view.locator('#st-body .page-head h2')).toBeVisible();
    await expect(view.locator('#st-body')).not.toContainText('Загрузка…');
  }
  // «Коды»: вкладка окон
  await view.locator('[data-st=codes]').click();
  await view.locator('[data-tab=windows]').click();
  await expect(view.locator('#cd-body')).toContainText('Окна и значения');
  // «Ночной обход»: вкладки
  await view.locator('[data-st=night]').click();
  await view.locator('[data-dtab=services]').click();
  await expect(view.locator('#dict-host')).toBeVisible();
  // «Расчёт»: смена шага расчёта попадает в черновик (последним: черновик не даёт уйти с экрана без подтверждения)
  await view.locator('[data-st=calc]').click();
  await view.locator('#cl-step button[data-v="30"]').click();
  await expect(view.locator('#cl-step button[data-v="30"]')).toHaveClass(/active/);
  await expect(view.locator('[data-draft-bar]')).not.toHaveClass(/idle/);
  expect(errors).toEqual([]);
});
