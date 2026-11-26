import { expect, test } from '@playwright/test';
import { login } from './helpers.mjs';

async function openBoard(page, user, width, height = 844) {
  await page.setViewportSize({ width, height });
  await login(page, user);
  await page.evaluate(() => window.navigate('stays'));
  const view = page.locator('#view-stays');
  await expect(view.locator('.sb-grid')).toBeVisible();
  return view;
}

for (const width of [320, 390]) {
  test(`мобильная шахматка на ${width}px показывает дату и объект и переносит сортировку в фильтры`, async ({ page }) => {
    const view = await openBoard(page, 'admin', width);
    await expect(view.locator('#sm-label')).toBeVisible();
    await expect(view.locator('#sf-q')).toBeVisible();
    await expect(view.locator('#sb-sort')).toBeHidden();
    await expect(view.locator('#sb-print')).toBeHidden();
    const grid = view.locator('.sb-grid');
    await view.locator('#sm-today').click();
    await expect.poll(() => grid.evaluate(el => {
      const day = el.querySelector('.sb-head .today').getBoundingClientRect();
      const unit = el.querySelector('.sb-head .sb-unit').getBoundingClientRect();
      const viewport = el.getBoundingClientRect();
      return unit.left >= viewport.left && day.left >= unit.right && day.right <= viewport.right;
    })).toBe(true);

    const filter = view.getByRole('button', { name: 'Фильтры' });
    await filter.click();
    await expect(view.getByLabel('Сортировка строк', { exact: true })).toBeVisible();
    await view.getByLabel('Сортировка строк', { exact: true }).selectOption('label');
    await expect(view.locator('.sf-panel').getByLabel('группировать по дереву')).toBeVisible();
    await expect(view.locator('#sf-saved')).toBeVisible();
    await view.locator('[data-sf-dd=cat] summary').click();
    await view.locator('[data-sf-cat]').first().check();
    await expect(filter).toHaveText(/Фильтры\s*\(1\)/);
    await view.locator('#sf-reset').click();
    await expect(filter).toHaveText('Фильтры');
  });
}

test('мобильная выгрузка группирует форматы с указанием состава данных по правам', async ({ page }) => {
  const view = await openBoard(page, 'admin', 390);
  const menu = view.locator('.sb-mobile-exports');
  const trigger = menu.locator('summary');
  await expect(trigger).toBeVisible();
  await trigger.press('Enter');
  const action = menu.getByRole('button', { name: 'Шахматка XLSX с данными гостей' });
  await expect(action).toBeVisible();
  await expect(menu.getByRole('button', { name: 'Сводка XLSX без данных гостей' })).toBeVisible();
  await expect(menu.getByRole('button', { name: 'Сводка XLSX с данными гостей' })).toBeVisible();
  const requested = page.waitForRequest(r => new URL(r.url()).pathname === '/api/stays/board/units/export');
  await action.click();
  expect(new URL((await requested).url()).searchParams.get('format')).toBe('xlsx');
  await expect(menu).not.toHaveAttribute('open', '');
  await expect(trigger).toBeFocused();
});

test('роль загрузки видит в мобильном меню выгрузки только варианты без данных гостей', async ({ page }) => {
  const view = await openBoard(page, 'sluzhba', 390);
  const menu = view.locator('.sb-mobile-exports');
  await menu.locator('summary').click();
  await expect(menu.getByRole('button', { name: 'Шахматка XLSX без данных гостей' })).toBeVisible();
  await expect(menu.getByRole('button', { name: /с данными гостей/ })).toHaveCount(0);
  await page.keyboard.press('Escape');
  await expect(menu).not.toHaveAttribute('open', '');
});

test('меню выгрузки закрывается при выходе по Tab и касании вне меню', async ({ page }) => {
  const view = await openBoard(page, 'admin', 390);
  const menu = view.locator('.sb-mobile-exports');
  const trigger = menu.locator('summary');
  await trigger.press('Enter');
  await expect(menu).toHaveAttribute('open', '');
  await menu.getByRole('button').last().focus();
  await page.keyboard.press('Tab');
  await expect(view.getByRole('button', { name: 'Фильтры' })).toBeFocused();
  await expect(menu).not.toHaveAttribute('open', '');

  await trigger.click();
  await expect(menu).toHaveAttribute('open', '');
  await view.getByRole('heading', { name: 'Шахматка' }).click();
  await expect(menu).not.toHaveAttribute('open', '');
});

test('на низком экране видны шапка сетки после «Сегодня» и все действия выгрузки', async ({ page }) => {
  const view = await openBoard(page, 'admin', 320, 568);
  await page.locator('main.content').evaluate(el => { el.scrollTop = el.scrollHeight; });
  await view.locator('#sm-today').click();
  await expect.poll(() => view.locator('.sb-head').evaluate(head => {
    const present = selector => {
      const target = head.querySelector(selector);
      const rect = target.getBoundingClientRect();
      return target.contains(document.elementFromPoint((rect.left + rect.right) / 2, (rect.top + rect.bottom) / 2));
    };
    return present('.sb-unit') && present('.today');
  })).toBe(true);

  const menu = view.locator('.sb-mobile-exports');
  await menu.locator('summary').click();
  await expect.poll(() => menu.getByRole('button').evaluateAll(items => items.every(item => {
    const rect = item.getBoundingClientRect();
    return item.contains(document.elementFromPoint((rect.left + rect.right) / 2, (rect.top + rect.bottom) / 2));
  }))).toBe(true);
});

test('просмотр фамилий сохраняет фильтр в PDF и убирает его из Excel без права выгрузки', async ({ page }) => {
  const view = await openBoard(page, 'rukovod', 390);
  const menu = view.locator('.sb-mobile-exports');
  await view.locator('#sf-q').fill('Орлов');
  await menu.locator('summary').click();
  const excel = menu.getByRole('button', { name: 'Шахматка XLSX без данных гостей' });
  await expect(excel).toBeEnabled();
  const path = '**/api/stays/board/units/export?**';
  await page.route(path, route => route.fulfill({ body: 'export fixture' }));
  const excelRequest = page.waitForRequest(path);
  await excel.click();
  const xlsx = new URL((await excelRequest).url()).searchParams;
  expect(xlsx.get('format')).toBe('xlsx');
  expect(xlsx.has('q')).toBe(false);

  await menu.locator('summary').click();
  const pdfRequest = page.waitForRequest(path);
  await menu.getByRole('button', { name: 'Шахматка PDF с данными гостей' }).click();
  const pdf = new URL((await pdfRequest).url()).searchParams;
  expect(pdf.get('format')).toBe('pdf');
  expect(pdf.get('q')).toBe('Орлов');
  expect(pdf.get('first')).toBe(xlsx.get('first'));
  expect(pdf.get('last')).toBe(xlsx.get('last'));
});
