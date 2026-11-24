/* «Ночной отчёт» и «Электрокары» (шаг 6е): уровни обхода, поиск, окна, история кара. */
import { expect, test } from '@playwright/test';
import { login, watchErrors } from './helpers.mjs';

const open = (page, view) => page.evaluate(v => window.navigate(v), view);

test('«Ночной отчёт»: зоны → объекты → чек-лист, поиск не теряет фокус, архив', async ({ page }) => {
  const errors = watchErrors(page);
  await login(page, 'admin');
  await open(page, 'night');
  const view = page.locator('#view-night');
  await expect(view.locator('#night-body')).not.toContainText('Загрузка…');
  await expect(view.locator('#night-archive')).toBeVisible();
  const zones = view.locator('[data-zone-open]');
  if (await zones.count()) {
    await zones.first().click();
    const q = view.locator('#night-obj-q');
    await expect(q).toBeVisible();
    await q.click();
    await page.keyboard.type('в', { delay: 60 });
    await expect(q).toBeFocused();
    await expect(q).toHaveValue('в');
    await q.fill('');
    await view.locator('[data-ofilter=all]').click();
    const first = view.locator('[data-sec-open]').first();
    if (await first.count()) {
      await first.click();
      await expect(view.locator('.night-area')).toBeVisible();
      await view.locator('[data-crumb=zones]').click();
      await expect(view.locator('[data-zone-open]').first()).toBeVisible();
    }
  }
  await view.locator('#night-archive').click();
  const modal = page.locator('#modal');
  await expect(modal).toContainText('Архив ночных отчётов');
  await modal.locator('[data-cancel]').click();
  expect(errors).toEqual([]);
});

test('«Электрокары»: список, фильтр, поиск и история кара', async ({ page }) => {
  const errors = watchErrors(page);
  await login(page, 'admin');
  await open(page, 'cars');
  const view = page.locator('#view-cars');
  await expect(view.locator('.stat-grid')).toBeVisible();
  const rows = view.locator('tbody tr');
  expect(await rows.count()).toBeGreaterThan(0);
  const q = view.locator('#cars-q');
  await q.click();
  await page.keyboard.type('zzzzz', { delay: 40 });
  await expect(q).toBeFocused();
  await expect(view.locator('tbody')).toContainText('Нет каров по фильтру');
  await q.fill('');
  await expect(rows.first()).not.toContainText('Нет каров по фильтру');
  /* «История» — вторичная операция: сидит в выпадающем меню «⋯» строки */
  await view.locator('[data-menu-btn]').first().click();
  await view.locator('.menu-wrap.open [data-act=history]').click();
  const modal = page.locator('#modal');
  await expect(modal).toContainText('История кара');
  await modal.locator('[data-cancel]').click();
  expect(errors).toEqual([]);
});

test('меню кара остаётся в viewport и не закрывается от собственного scroll', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 320 });
  await login(page, 'admin');
  await open(page, 'cars');
  const view = page.locator('#view-cars');
  const button = view.locator('[data-menu-btn]').first();
  await expect(button).toBeVisible();

  for (const corner of ['top-left', 'top-right', 'bottom-left', 'bottom-right']) {
    await button.evaluate((el, place) => {
      Object.assign(el.style, { position: 'fixed', zIndex: '80', left: 'auto', right: 'auto', top: 'auto', bottom: 'auto' });
      const [vertical, horizontal] = place.split('-');
      el.style[vertical] = '0px';
      el.style[horizontal] = '0px';
    }, corner);
    await button.click();
    const menu = view.locator('.menu-wrap.open .menu-pop');
    await expect(menu).toBeVisible();
    const box = await menu.boundingBox();
    expect.soft(box.x, `${corner}: left`).toBeGreaterThanOrEqual(8);
    expect.soft(box.y, `${corner}: top`).toBeGreaterThanOrEqual(8);
    expect.soft(box.x + box.width, `${corner}: right`).toBeLessThanOrEqual(382);
    expect.soft(box.y + box.height, `${corner}: bottom`).toBeLessThanOrEqual(312);
    await page.keyboard.press('Escape');
    await expect(menu).toBeHidden();
  }

  await button.evaluate(el => Object.assign(el.style, { top: 'auto', left: 'auto', right: '0px', bottom: '0px' }));
  await button.click();
  const menu = view.locator('.menu-wrap.open .menu-pop');
  await expect(menu).toBeVisible();
  await menu.evaluate(el => { el.style.maxHeight = '80px'; });
  expect(await menu.evaluate(el => el.scrollHeight > el.clientHeight)).toBe(true);
  await menu.evaluate(el => { el.scrollTop = 30; el.dispatchEvent(new Event('scroll')); });
  await expect(menu).toBeVisible();
  await expect(button).toHaveAttribute('aria-expanded', 'true');
});

test('меню кара управляется клавиатурой и возвращает фокус', async ({ page }) => {
  await login(page, 'admin');
  await open(page, 'cars');
  const view = page.locator('#view-cars');
  const button = view.locator('[data-menu-btn]').first();
  await button.focus();
  await page.keyboard.press('Enter');
  const items = view.locator('.menu-wrap.open [role=menuitem]');
  await expect(items.first()).toBeFocused();
  await page.keyboard.press('ArrowDown');
  await expect(items.nth(1)).toBeFocused();
  await page.keyboard.press('ArrowUp');
  await expect(items.first()).toBeFocused();
  await page.keyboard.press('Tab');
  await expect(view.locator('.menu-wrap.open')).toHaveCount(0);
  await expect(button).not.toBeFocused();
  await button.focus();
  await page.keyboard.press('Enter');
  await expect(view.locator('.menu-wrap.open [role=menuitem]').first()).toBeFocused();
  await page.keyboard.press('Escape');
  await expect(view.locator('.menu-wrap.open')).toHaveCount(0);
  await expect(button).toBeFocused();
});
