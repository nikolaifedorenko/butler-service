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
  await expect(main.locator('#sidenav-fold')).toBeHidden();
  expect((await main.boundingBox()).width).toBe(normal);
  await main.getByRole('button', { name: 'Настройки', exact: true }).click();
  await expect(expand).toBeVisible();
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
