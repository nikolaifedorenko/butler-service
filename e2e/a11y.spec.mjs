/* Доступность: автоматическая проверка axe (WCAG 2.1 A и AA) каждого раздела меню и каждого экрана
   «Настроек» под ролью, в светлой и тёмной теме. Ловит то, что видно без человека: подписи у кнопок и
   полей, контраст, роли и имена элементов. Клавиатуру и экранные читалки это не заменяет. */
import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';
import { login } from './helpers.mjs';

const ROLES = ['admin', 'ivanov', 'rukovod'];
const TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'];

async function scan(page, where) {
  const { violations } = await new AxeBuilder({ page }).withTags(TAGS).analyze();
  return violations.map(v => `${where}: ${v.id} (${v.impact}) ×${v.nodes.length} — ${v.help}; первый: ${v.nodes[0].target.join(' ')}`);
}

for (const scheme of ['light', 'dark']) {
  for (const username of ROLES) {
    test(`доступность (axe): ${username}, ${scheme}`, async ({ page }) => {
      test.setTimeout(300_000);
      await page.emulateMedia({ colorScheme: scheme });
      await login(page, username);
      const found = [];
      const views = await page.evaluate(() => window.state.menu.map(m => m.id));
      for (const view of ['today', ...views]) {
        await page.evaluate(v => window.navigate(v), view);
        await page.waitForTimeout(1200);
        found.push(...await scan(page, view));
      }
      if (views.includes('settings')) {
        await page.evaluate(() => window.navigate('settings'));
        await page.locator('#st-nav [data-st]').first().waitFor();
        const ids = await page.$$eval('#st-nav [data-st]', els => els.filter(b => !b.textContent.includes('↗')).map(b => b.dataset.st));
        for (const id of ids) {
          await page.locator(`#st-nav [data-st="${id}"]`).click();
          await page.waitForTimeout(900);
          found.push(...await scan(page, `settings/${id}`));
        }
      }
      expect([...new Set(found)], 'нарушения доступности').toEqual([]);
    });
  }
}

test('форма входа доступна (axe)', async ({ page }) => {
  await page.goto('/');
  await page.locator('#login-username').waitFor();
  expect(await scan(page, 'login')).toEqual([]);
});

test('открытое меню действий кара доступно (axe)', async ({ page }) => {
  await login(page, 'admin');
  await page.evaluate(() => window.navigate('cars'));
  const menuButton = page.locator('#view-cars [data-menu-btn]').first();
  await expect(menuButton).toBeVisible();
  await menuButton.click();
  await expect(page.locator('#view-cars .menu-wrap.open .menu-pop')).toBeVisible();
  expect(await scan(page, 'cars/open-menu')).toEqual([]);
});
