/* Основа интерфейса (шаг 6а): файлы подключаются как ES-модули, мост к общей области имён
   работает, lit-html экранирует вставки. Сценарии разделов добавляются по мере переноса. */
import { expect, test } from '@playwright/test';
import { login, watchErrors } from './helpers.mjs';

test('все скрипты оболочки — ES-модули', async ({ page }) => {
  await page.goto('/');
  const kinds = await page.$$eval('script[src]', els => els.map(e => e.type));
  expect(kinds.length).toBeGreaterThan(30);
  expect(new Set(kinds)).toEqual(new Set(['module']));
});

test('вход: форма, оболочка, мост имён, без ошибок консоли', async ({ page }) => {
  const errors = watchErrors(page);
  await login(page, 'gromova');
  // мост: имена модулей доступны в globalThis, а let-переменные — «живые»
  const bridge = await page.evaluate(() => ({
    fn: typeof window.navigate,
    state: typeof window.state?.user?.username,
    live: (() => { const before = window.pendingLoads; window.pendingLoads = before + 7;
                   const ok = window.pendingLoads === before + 7; window.pendingLoads = before; return ok; })(),
  }));
  expect(bridge).toEqual({ fn: 'function', state: 'string', live: true });
  await expect(page.locator('#nav, nav').first()).toBeVisible();
  expect(errors).toEqual([]);
});

test('неверный пароль: сообщение, оболочка не открывается', async ({ page }) => {
  await page.goto('/');
  await page.locator('#login-username').fill('gromova');
  await page.locator('#login-password').fill('неверный-пароль');
  await page.locator('#login-form button[type=submit]').click();
  await expect(page.locator('#login-error')).toBeVisible();
  await expect(page.locator('#app')).toHaveClass(/hidden/);
});

test('lit-html: разметка экранирует вставки', async ({ page }) => {
  await page.goto('/');
  const result = await page.evaluate(async () => {
    const { html, render } = await import('/static/js/ui/html.js');
    const host = document.createElement('div');
    const hostile = '<img src=x onerror="window.__pwned=1"><b>';
    render(html`<p class="t">${hostile}</p>`, host);
    document.body.appendChild(host);
    await new Promise(r => setTimeout(r, 50));
    return { text: host.querySelector('.t').textContent, imgs: host.querySelectorAll('img').length,
             pwned: window.__pwned ?? null };
  });
  expect(result).toEqual({ text: '<img src=x onerror="window.__pwned=1"><b>', imgs: 0, pwned: null });
});
