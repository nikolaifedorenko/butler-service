/* Обход разделов в настоящем браузере: каждый пункт меню роли открывается, рисует текст и не пишет
   ошибок в консоль. Это тот же смысл, что у смоука в jsdom (tools/ui_harness.mjs), но на реальных
   ES-модулях; смоук уходит, когда разделы переедут на модули (ADR-0013, раздел 7). */
import { expect, test } from '@playwright/test';
import { login, watchErrors } from './helpers.mjs';

const ROLES = ['gromova', 'ivanov', 'admin', 'rukovod', 'sluzhba'];

for (const username of ROLES) {
  test(`разделы меню открываются без ошибок: ${username}`, async ({ page }) => {
    test.setTimeout(120_000);
    const errors = watchErrors(page);
    await login(page, username);
    await page.locator('#sidenav .nav-item').first().waitFor();
    const views = await page.$$eval('#sidenav .nav-item', els => els.map(b => b.dataset.view).filter(Boolean));
    expect(views.length).toBeGreaterThan(0);
    for (const view of views) {
      await page.evaluate(v => window.navigate(v), view);
      await expect.poll(async () => page.locator(`#view-${view}`).evaluate(el => {
        const t = el.textContent.replace(/\s+/g, ' ').trim();
        return t.length > 0 && !t.includes('Загрузка…');
      }), { message: `раздел «${view}» не отрисовался`, timeout: 15_000 }).toBe(true);
    }
    expect(errors).toEqual([]);
  });
}
