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
