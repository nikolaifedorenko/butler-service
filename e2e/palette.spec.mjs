/* Палитра команд (⌘K / Ctrl+K): разделы, действия модулей, живой поиск гостей.
   Открытие/закрытие, навигация клавишами, переход и карточка гостя, Esc только палитру. */
import { expect, test } from '@playwright/test';
import { login, watchErrors } from './helpers.mjs';

const open = page => page.keyboard.press('Control+k');

test('палитра: разделы и действие «Создать бронь», поиск гостя, Esc', async ({ page }) => {
  const errors = watchErrors(page);
  await login(page, 'admin');
  await open(page);
  const box = page.locator('.palette');
  await expect(box.locator('input')).toBeFocused();
  await expect(box.locator('.palette-item').first()).toBeVisible();
  await expect(box.getByText('Создать бронь', { exact: true })).toBeVisible();

  /* стрелки + Enter: переход в раздел */
  await box.locator('input').fill('Шахматка');
  await expect(box.locator('.palette-item').first()).toContainText('Шахматка');
  await page.keyboard.press('Enter');
  await expect.poll(() => page.evaluate(() => window.state.view)).toBe('stays');
  await expect(page.locator('#palette-backdrop')).toBeHidden();

  /* живой поиск гостей — Enter открывает карточку drawer'ом */
  await open(page);
  await box.locator('input').fill('орло');
  await expect(box.locator('.palette-item').first()).toContainText('Орлов', { timeout: 8000 });
  await page.keyboard.press('Enter');
  await expect(page.locator('#drawer')).toContainText('История проживаний', { timeout: 8000 });

  /* Esc закрывает палитру и не трогает drawer под ней */
  await open(page);
  await expect(page.locator('#palette-backdrop')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.locator('#palette-backdrop')).toBeHidden();
  await expect(page.locator('#drawer-backdrop')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.locator('#drawer-backdrop')).toBeHidden();

  /* повторное Ctrl+K — закрывает */
  await open(page);
  await expect(page.locator('#palette-backdrop')).toBeVisible();
  await open(page);
  await expect(page.locator('#palette-backdrop')).toBeHidden();
  expect(errors).toEqual([]);
});
