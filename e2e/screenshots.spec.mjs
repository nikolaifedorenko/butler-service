/* Снимки интерфейса для документации и ревью: по скриншоту каждого раздела и экрана «Настроек» под
   ролью, светлая тема, десктоп и телефон. Запуск: SHOTS=1 npx playwright test e2e/screenshots.spec.mjs
   (результат — каталог ui-screenshots/, в репозиторий не попадает). */
import fs from 'node:fs';
import { test } from '@playwright/test';
import { login } from './helpers.mjs';

const OUT = 'ui-screenshots';
const ROLES = ['admin', 'gromova', 'ivanov'];

test.skip(!process.env.SHOTS, 'снимки делаются по запросу: SHOTS=1');

for (const username of ROLES) {
  for (const [kind, size] of [['desktop', { width: 1440, height: 900 }], ['mobile', { width: 390, height: 844 }]]) {
    test(`снимки: ${username}, ${kind}`, async ({ page }) => {
      test.setTimeout(300_000);
      fs.mkdirSync(OUT, { recursive: true });
      await page.setViewportSize(size);
      await page.emulateMedia({ colorScheme: 'light' });
      await login(page, username);
      const views = await page.evaluate(() => window.state.menu.map(m => m.id));
      for (const view of views) {
        await page.evaluate(v => window.navigate(v), view);
        await page.waitForTimeout(1200);
        await page.screenshot({ path: `${OUT}/${username}-${kind}-${view}.png`, fullPage: true });
      }
    });
  }
}
