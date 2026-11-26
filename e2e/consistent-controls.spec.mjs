import { expect, test } from '@playwright/test';
import { login } from './helpers.mjs';

test('форма входа показывает подписи, пустые поля и сохраняет автозаполнение', async ({ page }) => {
  await page.goto('/');
  const loginField = page.getByLabel('Логин', { exact: true });
  const password = page.getByLabel('Пароль', { exact: true });
  for (const [field, autocomplete] of [[loginField, 'username'], [password, 'current-password']]) {
    await expect(field).toHaveValue('');
    expect(await field.getAttribute('placeholder')).toBeNull();
    await expect(field).toHaveAttribute('autocomplete', autocomplete);
  }
});

test('стрелки месяца одинаково названы и управляют периодом в рабочих разделах', async ({ page }) => {
  await login(page, 'ivanov');
  for (const [view, host] of [['schedule', '#view-schedule'], ['stays', '#view-stays'], ['mystays', '#view-mystays']]) {
    await page.evaluate(view => window.navigate(view), view);
    const screen = page.locator(host);
    if (view === 'mystays') await screen.getByRole('button', { name: 'Мой месяц' }).click();
    const switcher = screen.locator('.month-nav');
    const prev = switcher.getByRole('button', { name: 'Предыдущий месяц' });
    const next = switcher.getByRole('button', { name: 'Следующий месяц' });
    for (const button of [prev, next]) await expect(button.locator('svg[aria-hidden="true"]')).toBeVisible();
    const label = switcher.locator('.label');
    await expect(label).toHaveText(/\d{4}/);
    const before = await label.textContent();
    await prev.focus();
    await page.keyboard.press('Enter');
    await expect(label).not.toHaveText(before);
    await expect(label).toHaveText(/\d{4}/);
  }
});

test('предпочтения гостя обозначены словами из его профиля', async ({ page }) => {
  await login(page, 'ivanov');
  const response = await page.request.get('/api/stays/mine/today');
  const data = await response.json();
  const guest = data.reservations.flatMap(reservation => reservation.guests)
    .find(guest => guest.preferences.allergy === 'орехи');
  guest.preferences['Время завтрака'] = '08:00';
  await page.route('**/api/stays/mine/today', route => route.fulfill({ json: data }));
  await page.evaluate(() => window.navigate('mystays'));
  const mine = page.locator('#view-mystays');
  await expect(mine).toContainText('Аллергия: орехи');
  await expect(mine).not.toContainText('allergy:');
  await expect(mine).toContainText('Время завтрака: 08:00');
  const card = mine.locator('.mine-guest').filter({ hasText: 'Аллергия: орехи' });
  await card.getByRole('button', { name: 'Карточка гостя' }).click();
  const dialog = page.locator('#modal');
  await expect(dialog).toContainText('Аллергия: орехи');
  await dialog.getByRole('button', { name: 'Семья, связи, пожелания' }).click();
  await expect(page.locator('#drawer')).toContainText('Аллергия: орехи');
});
