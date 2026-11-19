/* Длинные пользовательские пути разделов (бывшие сценарии jsdom, tools/*_scenario.mjs): каждая
   проверка сценария — отдельная строка отчёта; тест падает, если провалена хоть одна. */
import { expect, test } from '@playwright/test';
import { login } from '../helpers.mjs';
import { fundScenario } from './fund.mjs';
import { settingsScenario } from './settings.mjs';

/** Запуск функции-сценария в странице; возвращает строки с провалами. */
async function run(page, scenario, opts) {
  const lines = [];
  page.on('console', m => lines.push(m.text()));
  const result = await page.evaluate(scenario, opts);
  const failed = lines.filter(l => l.includes('❌'));
  expect(failed, `проверок пройдено ${result.passed}`).toEqual([]);
  expect(result.failed).toBe(0);
  expect(result.passed).toBeGreaterThan(0);
  test.info().annotations.push({ type: 'проверок', description: String(result.passed) });
}

test('«Настройки»: правила, мастер, проверитель, версия, поиск', async ({ page }) => {
  await login(page, 'admin');
  await run(page, settingsScenario, { LOGIN: 'admin' });
});

for (const who of ['admin', 'rukovod']) {
  test(`«Фонд и категории» под ${who}`, async ({ page }) => {
    await login(page, who);
    await run(page, fundScenario, { LOGIN: who });
  });
}
