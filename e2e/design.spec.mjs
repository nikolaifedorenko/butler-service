/* Дизайн-система (шаг 6б): страница-образец, тёмная тема, контраст основных пар, переключатель темы. */
import { expect, test } from '@playwright/test';
import { login, watchErrors } from './helpers.mjs';

/** Относительная яркость и контраст по WCAG 2.x. */
const CONTRAST_FN = `(a, b) => {
  const lum = c => { const [r, g, bl] = c.match(/[\\d.]+/g).slice(0, 3).map(Number).map(v => v / 255)
    .map(v => v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4); return 0.2126 * r + 0.7152 * g + 0.0722 * bl; };
  const [hi, lo] = [lum(a), lum(b)].sort((x, y) => y - x); return (hi + 0.05) / (lo + 0.05);
}`;

for (const mode of ['light', 'dark']) {
  test(`образец: основные пары текста проходят AA в теме «${mode}»`, async ({ page }) => {
    const errors = watchErrors(page);
    await page.addInitScript(m => localStorage.setItem('butler-theme', m), mode);
    await page.goto('/static/design.html');
    await expect(page.locator('html')).toHaveAttribute('data-theme', mode);
    const ratios = await page.$$eval('#ds-pairs .pair', (els, src) => {
      const contrast = eval(src);
      return els.map(e => { const s = getComputedStyle(e); return { name: e.textContent, ratio: contrast(s.color, s.backgroundColor) }; });
    }, CONTRAST_FN);
    expect(ratios.length).toBe(9);
    for (const r of ratios) expect(r.ratio, `${r.name} (${mode})`).toBeGreaterThanOrEqual(4.5);
    expect(errors).toEqual([]);
  });
}

test('тёмная тема действительно меняет поверхности и текст', async ({ page }) => {
  await page.goto('/static/design.html');
  const get = () => page.evaluate(() => { const s = getComputedStyle(document.body); return { bg: s.backgroundColor, fg: s.color }; });
  await page.evaluate(() => window.butlerTheme.set('light'));
  const light = await get();
  await page.evaluate(() => window.butlerTheme.set('dark'));
  const dark = await get();
  expect(dark.bg).not.toEqual(light.bg);
  expect(dark.fg).not.toEqual(light.fg);
});

test('«как в системе» следует prefers-color-scheme', async ({ page }) => {
  await page.emulateMedia({ colorScheme: 'dark' });
  await page.goto('/static/design.html');
  await page.evaluate(() => window.butlerTheme.set('auto'));
  await expect(page.locator('html')).not.toHaveAttribute('data-theme', /.+/);
  const bgDark = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
  await page.emulateMedia({ colorScheme: 'light' });
  const bgLight = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
  expect(bgDark).not.toEqual(bgLight);
});

test('переключатель темы в приложении: светлая → тёмная → система, выбор переживает перезагрузку', async ({ page }) => {
  const errors = watchErrors(page);
  await login(page, 'gromova');
  const mode = () => page.locator('html').getAttribute('data-theme-mode');
  expect(await mode()).toBe('auto');
  await page.locator('#theme-toggle').click();
  expect(await mode()).toBe('light');
  await page.locator('#theme-toggle').click();
  expect(await mode()).toBe('dark');
  await page.reload();
  await page.locator('#app:not(.hidden)').waitFor();
  expect(await mode()).toBe('dark');
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  await page.locator('#theme-toggle').click();     // dark → auto
  expect(await mode()).toBe('auto');
  expect(errors).toEqual([]);
});

test('образец содержит все компоненты', async ({ page }) => {
  await page.goto('/static/design.html');
  for (const sel of ['.btn-primary', '.btn-danger', 'input[type=text]', 'select', '.badge.ok', '.stat', '.seg',
                     '.panel', '.alert.warn', '.modal', '.toast', '.drawer']) {
    await expect(page.locator(`main ${sel}`).first(), sel).toBeVisible();
  }
});

for (const mode of ['light', 'dark']) {
  test(`модальное окно и уведомление берут фон поверхности, а не тон сообщения (${mode})`, async ({ page }) => {
    await page.addInitScript(m => localStorage.setItem('butler-theme', m), mode);
    await login(page, 'admin');
    await page.evaluate(() => {
      window.openModal({ title: 'Проба', body: 'текст' });
      window.toast('Проба', 'ok');
    });
    const colors = await page.evaluate(() => {
      const surface = getComputedStyle(document.documentElement).getPropertyValue('--surface-0').trim();
      const probe = document.createElement('div'); probe.style.background = surface; document.body.appendChild(probe);
      const expected = getComputedStyle(probe).backgroundColor; probe.remove();
      return { expected, modal: getComputedStyle(document.querySelector('#modal')).backgroundColor,
               toast: getComputedStyle(document.querySelector('#toast-host .toast')).backgroundColor };
    });
    expect(colors.modal).toBe(colors.expected);
    expect(colors.toast).toBe(colors.expected);
  });
}
