/* Сценарии интерфейса в настоящем браузере (ADR-0013, раздел 7). Каталог — e2e/.
   Сервер поднимает tools/e2e_server.sh на свежей демо-базе; запуск: npm run e2e. */
import { defineConfig, devices } from '@playwright/test';

const PORT = Number(process.env.E2E_PORT || 8180);

export default defineConfig({
  testDir: './e2e',
  testMatch: '**/*.spec.mjs',
  fullyParallel: false,       // одна демо-база на все сценарии
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : 'list',
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    trace: 'retain-on-failure',
    locale: 'ru-RU',
    timezoneId: 'Europe/Moscow',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: {
    command: `./tools/e2e_server.sh ${PORT}`,
    url: `http://127.0.0.1:${PORT}/api/health`,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
});
