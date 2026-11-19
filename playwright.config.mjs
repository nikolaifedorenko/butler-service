/* Сценарии интерфейса в настоящем браузере (ADR-0013, раздел 7). Каталог — e2e/.
   Три сервера на свежих демо-базах: основной (быстрые проверки разделов), сценарии (длинные
   пути с изменением данных — своя база, чтобы не мешать остальным) и «ночной» (пояс подобран так,
   чтобы шла ночная смена). Запуск: npm run e2e. */
import { defineConfig, devices } from '@playwright/test';

const PORT = Number(process.env.E2E_PORT || 8180);
const SCN_PORT = PORT + 1;
const NIGHT_PORT = PORT + 2;
const server = (port, db, mode = '') => ({
  command: `./tools/e2e_server.sh ${port} ${db} ${mode}`,
  url: `http://127.0.0.1:${port}/api/health`,
  reuseExistingServer: !process.env.CI,
  timeout: 120_000,
});

export default defineConfig({
  testDir: './e2e',
  testMatch: '**/*.spec.mjs',
  fullyParallel: false,       // одна демо-база на проект
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : 'list',
  use: {
    trace: 'retain-on-failure',
    locale: 'ru-RU',
    timezoneId: 'Europe/Moscow',
  },
  projects: [
    { name: 'chromium', testIgnore: '**/scenarios/**',
      use: { ...devices['Desktop Chrome'], baseURL: `http://127.0.0.1:${PORT}` } },
    { name: 'scenarios', testMatch: '**/scenarios/scenarios.spec.mjs', timeout: 300_000,
      use: { ...devices['Desktop Chrome'], baseURL: `http://127.0.0.1:${SCN_PORT}` } },
    { name: 'night', testMatch: '**/scenarios/night.spec.mjs', timeout: 300_000,
      use: { ...devices['Desktop Chrome'], baseURL: `http://127.0.0.1:${NIGHT_PORT}` } },
  ],
  webServer: [server(PORT, 'e2e'), server(SCN_PORT, 'e2e_scn'), server(NIGHT_PORT, 'e2e_night', 'night')],
});
