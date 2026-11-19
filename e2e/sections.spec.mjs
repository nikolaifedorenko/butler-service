/* Обход разделов в настоящем браузере (бывший смоук интерфейса): каждый пункт меню роли и каждый экран
   «Настроек» открывается, рисует текст без «Загрузка…» и мусора (undefined, NaN, [object Object]) и не
   пишет ошибок в консоль. Роли — по одной на уровень доступа. */
import { expect, test } from '@playwright/test';
import { login, watchErrors } from './helpers.mjs';

const ROLES = ['gromova', 'ivanov', 'admin', 'rukovod', 'sluzhba'];
const JUNK = /undefined|NaN|\[object Object\]/;

/** Ждёт, пока контейнер нарисует текст; возвращает его HTML для проверки на мусор. */
async function rendered(page, selector, what) {
  await expect.poll(async () => page.locator(selector).evaluate(el => {
    const t = el.textContent.replace(/\s+/g, ' ').trim();
    return t.length > 0 && !t.includes('Загрузка…');
  }), { message: `${what} не отрисовался`, timeout: 15_000 }).toBe(true);
  return page.locator(selector).evaluate(el => el.innerHTML);
}

for (const username of ROLES) {
  test(`разделы меню открываются без ошибок и мусора: ${username}`, async ({ page }) => {
    test.setTimeout(180_000);
    const errors = watchErrors(page);
    await login(page, username);
    await page.locator('#sidenav .nav-item').first().waitFor();
    const views = await page.$$eval('#sidenav .nav-item', els => els.map(b => b.dataset.view).filter(Boolean));
    expect(views.length).toBeGreaterThan(0);
    const junk = [];
    for (const view of views) {
      await page.evaluate(v => window.navigate(v), view);
      const html = await rendered(page, `#view-${view}`, `раздел «${view}»`);
      if (JUNK.test(html.replace(/<[^>]*>/g, ' '))) junk.push(view);
    }
    /* экраны Настроек приходят из манифестов: в навигации должны быть все, а не часть */
    if (views.includes('settings')) {
      await page.evaluate(() => window.navigate('settings'));
      await page.locator('#st-nav [data-st]').first().waitFor();
      const expected = await page.evaluate(() => (window.state.settingsScreens || []).filter(s => !s.external).length);
      const ids = await page.$$eval('#st-nav [data-st]', els => els.filter(b => !b.textContent.includes('↗')).map(b => b.dataset.st));
      expect(ids.length, 'в под-навигации не все экраны из манифестов').toBe(expected);
      for (const id of ids) {
        await page.locator(`#st-nav [data-st="${id}"]`).click();
        const html = await rendered(page, '#st-body', `экран настроек «${id}»`);
        if (JUNK.test(html.replace(/<[^>]*>/g, ' '))) junk.push(`settings/${id}`);
      }
    }
    expect(junk, 'в разметке остался undefined / NaN / [object Object]').toEqual([]);
    expect(errors).toEqual([]);
  });
}
