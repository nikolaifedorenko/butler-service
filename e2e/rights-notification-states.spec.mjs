import { expect, test } from '@playwright/test';
import { login } from './helpers.mjs';

test('права роли свернуты по разделам и раскрываются с клавиатуры', async ({ page }) => {
  await login(page, 'admin');
  const data = await (await page.request.get('/api/access')).json();
  const role = data.roles[0];
  const section = data.permissions[0].section;
  const permissions = data.permissions.filter(permission => permission.section === section);
  const allowed = permissions.filter(permission => role.effective.includes(permission.key)).length;
  await page.evaluate(() => window.navigate('access'));
  const roleSummary = page.locator('[data-role-summary]').first();
  const module = roleSummary.locator('details').filter({ has: page.locator('summary', { hasText: section }) });
  const label = module.locator('summary');
  await expect(label).toContainText(`${allowed} из ${permissions.length}`);
  const permission = module.getByText(permissions[0].title, { exact: true });
  await expect(permission).toBeHidden();
  await label.focus();
  await page.keyboard.press('Enter');
  await expect(permission).toBeVisible();
  await page.keyboard.press('Enter');
  await expect(permission).toBeHidden();
});

test('сворачивание раздела не сбрасывает изменённое право при сохранении', async ({ page }) => {
  await login(page, 'admin');
  const data = await (await page.request.get('/api/access')).json();
  const role = data.roles[0], permission = data.permissions.find(p => !role.overrides[p.key]);
  const endpoint = `**/api/access/roles/${role.role}`;
  await page.route(endpoint, route => route.fulfill({ json: { ok: true } }));
  await page.evaluate(() => window.navigate('access'));
  await page.locator('[data-role]').first().click();
  const dialog = page.getByRole('dialog', { name: /Права роли/ });
  const summary = dialog.locator('summary').filter({ hasText: permission.section }).first();
  await summary.click();
  const count = summary.locator('[data-grant-count]');
  const before = Number(await count.textContent());
  const select = dialog.getByLabel(permission.title, { exact: true });
  await select.selectOption('deny');
  await expect(count).toHaveText(String(before + 1));
  await summary.click();
  await expect(select).toBeHidden();
  const saved = page.waitForRequest(request => request.method() === 'PUT' && request.url().endsWith('/roles/' + role.role));
  await dialog.getByRole('button', { name: 'Сохранить' }).click();
  expect((await saved).postDataJSON().grants[permission.key]).toBe('deny');
});

test('состояние сценария не меняется из-за настройки каналов, приём письма требует подтверждения', async ({ page }) => {
  await login(page, 'admin');
  const data = await (await page.request.get('/api/notify/config')).json();
  await page.route('**/api/notify/config', route => route.fulfill({ json: {
    ...data, config: { ...data.config, ready: { telegram: true, email: false } },
  } }));
  let confirmed = false;
  await page.route('**/api/notify/email/test', route => route.fulfill({ json: confirmed ? { message_id: 'test-message' } : {} }));
  await page.evaluate(() => window.navigate('settings'));
  await page.locator('#st-nav [data-st="notify"]').click();
  const settings = page.locator('#st-body');
  await expect(settings.getByRole('columnheader', { name: 'Состояние сценария' })).toBeVisible();
  await expect(settings.getByRole('row', { name: /Ночной отчёт/ })).toContainText('Доступен');
  await expect(settings.locator('[data-notify-channel="telegram"]')).toContainText('Настроен');
  await expect(settings.locator('[data-notify-channel="email"]')).toContainText('Не настроена');
  await settings.locator('#ne-test-to').fill('test@example.invalid');
  const send = settings.getByRole('button', { name: 'Отправить тестовое письмо' });
  await send.click();
  const result = settings.getByRole('status', { name: 'Результат отправки письма' });
  await expect(result).toContainText('Почтовый сервер не подтвердил приём письма');
  confirmed = true;
  await send.click();
  await expect(result).toContainText('Почтовый сервер принял тестовое письмо');
});

test('заполненный SMTP с нечитаемым паролем требует повторного ввода', async ({ page }) => {
  await login(page, 'admin');
  const data = await (await page.request.get('/api/notify/config')).json();
  await page.route('**/api/notify/config', route => route.fulfill({ json: {
    ...data, config: { ...data.config, email: { ...data.config.email, user: 'mailer' },
      ready: { ...data.config.ready, email: true }, unreadable: ['notify_smtp_password'] },
  } }));
  await page.evaluate(() => window.navigate('settings'));
  await page.locator('#st-nav [data-st="notify"]').click();
  const email = page.locator('#st-body [data-notify-channel="email"]');
  await expect(email).toContainText('Введите пароль заново');
  await expect(email).not.toContainText('Настроена');
});
