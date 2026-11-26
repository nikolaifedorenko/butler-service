import { expect, test } from '@playwright/test';
import { login } from './helpers.mjs';

const navigate = (page, view) => page.evaluate(view => window.navigate(view), view);

test('на компьютере настройки сворачивают основное меню, сохраняя названия и доступ с клавиатуры', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 850 });
  await login(page, 'admin');
  const main = page.locator('#sidenav');
  const normal = (await main.boundingBox()).width;
  await navigate(page, 'settings');
  const settings = page.locator('#st-nav');
  await expect(settings.getByRole('button', { name: 'Расчёт', exact: true })).toBeVisible();
  expect((await main.boundingBox()).width).toBeLessThan(normal / 2);
  const chessboard = main.getByRole('button', { name: 'Шахматка' });
  await expect(chessboard).toBeVisible();
  await chessboard.focus();
  const tip = page.locator('#sidenav-tooltip');
  await expect(tip).toHaveText('Шахматка');
  await expect(tip).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(tip).toBeHidden();
  const expand = main.getByRole('button', { name: 'Развернуть основное меню' });
  await expand.focus();
  await page.keyboard.press('Enter');
  await expect(expand).toHaveCount(0);
  const collapse = main.getByRole('button', { name: 'Свернуть основное меню' });
  await expect(collapse).toBeFocused();
  await expect(collapse).toHaveAttribute('aria-expanded', 'true');
  expect((await main.boundingBox()).width).toBe(normal);
  await settings.locator('[data-st="calc"]').click();
  expect((await main.boundingBox()).width).toBe(normal);
  await navigate(page, 'access');
  await expect(page.locator('#view-access')).toBeVisible();
  await main.getByRole('button', { name: 'Настройки', exact: true }).click();
  await expect(collapse).toBeVisible();
  await main.getByRole('button', { name: 'Сегодня', exact: true }).click();
  await expect(collapse).toBeVisible();
  expect((await main.boundingBox()).width).toBe(normal);
  await main.getByRole('button', { name: 'Настройки', exact: true }).click();
  await expect(collapse).toBeVisible();
});

test('основное меню сворачивается на любом экране и запоминает выбор отдельно по аккаунтам', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 850 });
  await login(page, 'admin');
  const nav = page.locator('#sidenav');
  const fold = page.locator('#sidenav-fold');
  await expect(fold).toHaveAccessibleName('Свернуть основное меню');
  await expect(fold).toBeVisible();
  await fold.focus();
  await page.keyboard.press('Enter');
  await expect(fold).toBeFocused();
  await expect(fold).toHaveAccessibleName('Развернуть основное меню');
  await expect(fold).toHaveAttribute('aria-expanded', 'false');
  await expect(nav).toHaveClass(/compact/);

  const board = nav.getByRole('button', { name: 'Шахматка' });
  await board.focus();
  await page.keyboard.press('Enter');
  await expect(page.locator('#view-stays')).toBeVisible();
  await expect(board).toBeFocused();
  await expect(nav).toHaveClass(/compact/);
  await nav.getByRole('button', { name: 'Настройки' }).click();
  await expect(page.locator('#view-settings')).toBeVisible();
  await expect(nav).toHaveClass(/compact/);
  await page.reload();
  await expect(page.locator('#view-today.active')).toBeVisible();
  await expect(nav).toHaveClass(/compact/);

  await page.locator('#logout-btn').click();
  await expect(page.locator('#login-screen')).toBeVisible();
  await login(page, 'sluzhba');
  await expect(fold).toBeVisible();
  await expect(fold).toHaveAttribute('aria-expanded', 'true');
  await expect(nav).not.toHaveClass(/compact/);
  await page.locator('#logout-btn').click();
  await expect(page.locator('#login-screen')).toBeVisible();
  await login(page, 'admin');
  await expect(nav).toHaveClass(/compact/);
  await fold.click();
  await navigate(page, 'settings');
  await expect(fold).toHaveAttribute('aria-expanded', 'true');
  await expect(nav).not.toHaveClass(/compact/);
});

test('подсказка названия остаётся при прокрутке меню с клавиатуры', async ({ page }) => {
  await page.setViewportSize({ width: 1024, height: 420 });
  await login(page, 'admin');
  await navigate(page, 'settings');
  const nav = page.locator('#sidenav');
  await nav.locator('#sidenav-fold').focus();
  const guests = nav.getByRole('button', { name: 'Мои гости', exact: true });
  for (let i = 0; i < 14 && !await guests.evaluate(button => button === document.activeElement); i++) {
    await page.keyboard.press('Tab');
  }
  await expect(guests).toBeFocused();
  expect(await nav.evaluate(node => node.scrollTop)).toBeGreaterThan(0);
  const tooltip = page.locator('#sidenav-tooltip');
  await expect(tooltip).toBeVisible();
  await expect(tooltip).toHaveText('Мои гости');
});

test('панель публикации показывается только при изменениях и исчезает после сброса', async ({ page }) => {
  await login(page, 'admin');
  await navigate(page, 'settings');
  await page.locator('#st-nav [data-st="calc"]').click();
  const view = page.locator('#st-body');
  const bar = view.locator('[data-draft-bar]');
  const change = view.locator('#cl-step button[data-v]:not(.active)').first();
  await expect(change).toBeVisible();
  await expect(bar).toBeHidden();
  await change.click();
  await expect(bar).toBeVisible();
  await expect(bar.locator('[data-draft-publish]')).toBeEnabled();
  expect(await bar.evaluate(element => getComputedStyle(element).position)).toBe('sticky');
  await bar.locator('[data-draft-reset]').click();
  await page.getByRole('dialog', { name: 'Сбросить черновик?' }).getByRole('button', { name: 'Сбросить', exact: true }).click();
  await expect(bar).toBeHidden();
});

test('на телефоне настройки используют существующую нижнюю навигацию', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await login(page, 'admin');
  await navigate(page, 'settings');
  await expect(page.locator('#view-settings')).toBeVisible();
  await expect(page.locator('#tabbar')).toBeVisible();
  await expect(page.locator('#sidenav-fold')).toBeHidden();
});

test('режим просмотра глазами сотрудника не меняет сохранённую ширину меню', async ({ page }) => {
  await login(page, 'admin');
  const nav = page.locator('#sidenav');
  const fold = nav.locator('#sidenav-fold');
  await fold.click();
  await expect(nav).toHaveClass(/compact/);
  await navigate(page, 'employees');
  await page.locator('#view-employees tr[data-card]').filter({ hasText: 'Иванов' }).first().click();
  await page.locator('#modal [data-imp]').click();
  await expect(page.locator('#impersonation-bar')).toBeVisible();
  await expect(fold).toHaveAttribute('aria-expanded', 'true');
  await fold.click();
  await expect(nav).toHaveClass(/compact/);
  await fold.click();
  await expect(nav).not.toHaveClass(/compact/);

  await page.locator('#stop-impersonation').click();
  await expect(page.locator('#impersonation-bar')).toBeHidden();
  await expect(nav).toHaveClass(/compact/);
  await expect(fold).toHaveAttribute('aria-expanded', 'false');
});
