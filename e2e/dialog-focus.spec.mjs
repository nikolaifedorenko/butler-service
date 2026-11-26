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

test('Tab проходит прокручиваемый текст до кнопок и замыкается внутри диалога', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 720 });
  await login(page, 'admin');
  await page.evaluate(async () => {
    const { openModal } = await import('/static/js/core.js');
    const { html } = await import('/static/js/ui/html.js');
    openModal({
      title: 'Длинное уведомление',
      body: html`<p style="min-height: 1500px">Текст уведомления</p>`,
      footer: html`<button>Подтвердить</button>`,
    });
  });
  const modal = page.locator('#modal');
  const close = modal.getByRole('button', { name: 'Закрыть' });
  const content = modal.locator('.modal-body');
  const confirm = modal.getByRole('button', { name: 'Подтвердить' });

  await expect(close).toBeFocused();
  await page.keyboard.press('Tab');
  await expect(content).toBeFocused();
  await page.keyboard.press('Tab');
  await expect(confirm).toBeFocused();
  await page.keyboard.press('Tab');
  await expect(close).toBeFocused();
  await page.keyboard.press('Shift+Tab');
  await expect(confirm).toBeFocused();
  await page.keyboard.press('Shift+Tab');
  await expect(content).toBeFocused();
  await page.keyboard.press('Shift+Tab');
  await expect(close).toBeFocused();
});

test('перерисованная боковая карточка получает фокус поверх семейного окна', async ({ page }) => {
  await login(page, 'admin');
  await page.evaluate(async () => {
    const { openDrawer, openModal } = await import('/static/js/core.js');
    openDrawer({ title: 'Исходная карточка', body: 'Гость' });
    openModal({
      title: 'Семейные связи',
      body: 'Родственники',
      background: document.getElementById('drawer'),
    });
    openDrawer({ title: 'Обновлённая карточка', body: 'Гость' });
  });

  const drawer = page.getByRole('dialog', { name: 'Обновлённая карточка' });
  await expect(drawer.getByRole('button', { name: 'Закрыть' })).toBeFocused();
  await page.keyboard.press('Escape');
  const modal = page.getByRole('dialog', { name: 'Семейные связи' });
  await expect(modal.getByRole('button', { name: 'Закрыть' })).toBeFocused();
});
