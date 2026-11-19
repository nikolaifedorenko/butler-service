/* Ночной обход: сценарии идут при открытой ночной смене (сервер с поясом, где сейчас ~23:00). */
import { expect, test } from '@playwright/test';
import { login } from '../helpers.mjs';
import { nightCarsScenario } from './night_cars.mjs';
import { nightZonesScenario } from './night_zones.mjs';

async function run(page, scenario, opts) {
  const lines = [];
  page.on('console', m => lines.push(m.text()));
  const result = await page.evaluate(scenario, opts);
  expect(lines.filter(l => l.includes('❌')), `проверок пройдено ${result.passed}`).toEqual([]);
  expect(result.failed).toBe(0);
  expect(result.passed).toBeGreaterThan(0);
  test.info().annotations.push({ type: 'проверок', description: String(result.passed) });
}

test('электрокары в ночном обходе: окно отметки = окно возврата, фото', async ({ page }) => {
  await login(page, 'gromova');
  await run(page, nightCarsScenario, { LOGIN: 'gromova' });
});

test('ночной обход: зоны, объекты, чек-лист, справочник, службы', async ({ page }) => {
  await login(page, 'admin');
  await run(page, nightZonesScenario, { LOGIN: 'admin' });
});
