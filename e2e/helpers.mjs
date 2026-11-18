/* Общие помощники сценариев: вход под демо-учёткой и сбор ошибок. */
export const DEMO_PASSWORD = 'demo1234';

/** Ошибки с момента вызова: исключения страницы, ошибки консоли и ответы сервера 5xx.
    Ответы 4xx (401 до входа, 403/404 для роли без данных раздела) — штатные ответы API, их
    разбирает код интерфейса; браузер пишет их в консоль сам («Failed to load resource»),
    поэтому такие строки не считаются ошибкой кода. */
export function watchErrors(page) {
  const errors = [];
  page.on('pageerror', e => errors.push(`pageerror: ${e.message}`));
  page.on('console', m => {
    if (m.type() === 'error' && !m.text().startsWith('Failed to load resource')) errors.push(`console: ${m.text()}`);
  });
  page.on('response', r => { if (r.status() >= 500) errors.push(`${r.status()} ${r.url()}`); });
  return errors;
}

/** Войти через форму входа и дождаться, пока приложение откроет стартовый экран «Сегодня»: пока
    enterApp() не закончил, его navigate() перебил бы раздел, открытый сценарием. */
export async function login(page, username) {
  await page.goto('/');
  await page.locator('#login-username').fill(username);
  await page.locator('#login-password').fill(DEMO_PASSWORD);
  await page.locator('#login-form button[type=submit]').click();
  await page.locator('#app:not(.hidden)').waitFor();
  await page.locator('#view-today.active').waitFor();
}
