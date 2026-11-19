/* Телефон (375 px): каждый раздел меню помещается в ширину окна, прокручивается только внутри
   своих таблиц и сеток; кнопки и поля нажимаются пальцем (шаг 6и). */
import { expect, test } from '@playwright/test';
import { login, watchErrors } from './helpers.mjs';

const ROLES = ['admin', 'ivanov', 'rukovod', 'gromova'];

/* ширина страницы и элементы, вылезающие за правый край окна не внутри прокручиваемого блока */
const measure = () => {
  const vw = window.innerWidth;
  const scrolls = el => { for (let p = el.parentElement; p && !p.classList.contains('view') && p.id !== 'modal'; p = p.parentElement) {
    const o = getComputedStyle(p).overflowX; if (o === 'auto' || o === 'scroll') return true; } return false; };
  const out = [];
  document.querySelectorAll('.view.active *, #modal *').forEach(el => {
    const r = el.getBoundingClientRect();
    if (r.width && r.right > vw + 1 && !scrolls(el)) out.push(`${el.tagName.toLowerCase()}${el.id ? '#' + el.id : ''}.${String(el.className).split(' ')[0]}`);
  });
  /* цели нажатия: кнопки .btn, списки и поля ввода — не ниже 40 px */
  document.querySelectorAll('.view.active .btn, .view.active select, .view.active input:not([type=checkbox]):not([type=radio]):not([type=color]):not([type=file])').forEach(el => {
    const r = el.getBoundingClientRect();
    if (r.width && r.height && r.height < 39) out.push(`низкая цель ${el.tagName.toLowerCase()}.${String(el.className).split(' ')[0]} ${Math.round(r.height)}px`);
  });
  return { page: document.documentElement.scrollWidth - vw, out: [...new Set(out)].slice(0, 8) };
};

for (const role of ROLES) {
  test(`телефон: разделы роли ${role} не шире окна`, async ({ page }) => {
    test.setTimeout(240_000);
    const errors = watchErrors(page);
    await page.setViewportSize({ width: 375, height: 812 });
    await login(page, role);
    const views = await page.evaluate(() => window.state.menu.map(m => m.id));
    const bad = [];
    for (const v of [...new Set(views)]) {
      await page.evaluate(id => window.navigate(id), v);
      await page.waitForTimeout(700);
      const m = await page.evaluate(measure);
      if (m.page > 0 || m.out.length) bad.push(`${v}: страница +${m.page}px, ${m.out.join(', ')}`);
    }
    /* экраны Настроек — по списку, который сервер отдал этой роли */
    const screens = !views.includes('settings') ? [] : await page.evaluate(() => (window.state.settingsScreens || []).map(x => x.id || x).filter(Boolean));
    if (screens.length) await page.evaluate(() => window.navigate('settings'));
    for (const id of screens) {
      /* внешние экраны («Права», «Журнал») уводят из Настроек — возвращаемся */
      if (!(await page.locator('#view-settings #st-pick').isVisible())) await page.evaluate(() => window.navigate('settings'));
      await page.locator('#view-settings #st-pick').click();
      const item = page.locator(`#modal [data-st-pick="${id}"]`);
      if (!(await item.count())) { await page.locator('#modal .x').click(); continue; }
      await item.click();
      await page.waitForTimeout(500);
      const m = await page.evaluate(measure);
      if (m.page > 0 || m.out.length) bad.push(`settings/${id}: страница +${m.page}px, ${m.out.join(', ')}`);
    }
    expect(bad).toEqual([]);
    expect(errors).toEqual([]);
  });
}
