import { expect, test } from '@playwright/test';
import { login } from './helpers.mjs';

test('карточка брони получает доступное имя и удерживает фокус до закрытия', async ({ page }) => {
  await login(page, 'admin');
  await page.evaluate(() => window.navigate('stays'));
  await page.locator('[data-stab=bookings]').click();
  const booking = page.locator('tr.bk-row').first();
  await booking.focus();
  await page.keyboard.press('Enter');

  const dialog = page.locator('#modal');
  const close = dialog.getByRole('button', { name: 'Закрыть', exact: true }).first();
  const footer = dialog.locator('.modal-foot button').last();
  await expect(dialog).toBeVisible();
  await expect.soft(dialog).toHaveAccessibleName(/Бронь/);
  await expect.soft(close).toBeFocused();
  await page.keyboard.press('Shift+Tab');
  await expect.soft(footer).toBeFocused();
  await page.keyboard.press('Tab');
  await expect.soft(close).toBeFocused();
  await page.keyboard.press('Escape');
  await expect(dialog).toBeHidden();
  await expect(booking).toBeFocused();
});

test('вложенная модалка удерживает фокус и возвращает его в боковую карточку', async ({ page }) => {
  await login(page, 'admin');
  const opener = page.locator('#sidenav [data-view=today]');
  await opener.focus();
  await page.evaluate(async () => {
    const { openDrawer, openModal } = await import('/static/js/core.js');
    const { html } = await import('/static/js/ui/html.js');
    openDrawer({
      title: 'Карточка гостя',
      body: html`<button @click=${() => openModal({
        title: 'Редактирование гостя',
        body: html`
          <input aria-label="Имя">
          <button hidden>Скрытая кнопка</button>
          <button disabled>Недоступная кнопка</button>`,
        onMount(dialog) { dialog.querySelector('input').focus(); },
      })}>Редактировать</button>`,
    });
  });

  const drawer = page.locator('#drawer');
  const edit = drawer.getByRole('button', { name: 'Редактировать' });
  await expect.soft(drawer).toHaveAccessibleName('Карточка гостя');
  await expect.soft(drawer.getByRole('button', { name: 'Закрыть' })).toBeFocused();
  await edit.focus();
  await page.keyboard.press('Enter');

  const modal = page.locator('#modal');
  const close = modal.getByRole('button', { name: 'Закрыть' });
  await expect(modal.getByRole('textbox', { name: 'Имя' })).toBeFocused();
  await page.keyboard.press('Tab');
  await expect.soft(close).toBeFocused();
  await page.keyboard.press('Escape');
  await expect(modal).toBeHidden();
  await expect(drawer).toBeVisible();
  await expect(edit).toBeFocused();
  await page.keyboard.press('Escape');
  await expect(drawer).toBeHidden();
  await expect(opener).toBeFocused();
});
