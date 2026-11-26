import { expect, test } from '@playwright/test';
import { login } from './helpers.mjs';

async function board(page, user = 'admin') {
  await login(page, user);
  await page.evaluate(() => window.navigate('stays'));
  const grid = page.locator('#view-stays .sb-grid');
  await expect(grid).toBeVisible();
  return grid;
}

test('шахматка даёт одну остановку Tab и открывает выбранную стрелками бронь', async ({ page }) => {
  const grid = await board(page);
  const selected = grid.locator('button.sb-bar[tabindex="0"]');
  await expect(selected).toHaveCount(1);
  await page.locator('#view-stays .sb-exports summary').focus();
  await page.keyboard.press('Tab');
  await expect(selected).toBeFocused();
  const [firstId, nextId] = await grid.evaluate(el => {
    const rows = [...el.querySelectorAll('[data-unit-row]')].filter(row => row.querySelector('.sb-bar'));
    const index = rows.findIndex(row => row.querySelectorAll('.sb-bar').length > 1);
    return [rows[index]?.dataset.unitRow, rows[index + 1]?.dataset.unitRow];
  });
  expect(firstId).toBeTruthy();
  expect(nextId).toBeTruthy();
  const row = grid.locator(`[data-unit-row="${firstId}"]`);
  const ordered = await row.locator('.sb-bar').evaluateAll(bars =>
    bars.sort((a, b) => Number.parseFloat(a.style.left) - Number.parseFloat(b.style.left))
      .map(b => b.dataset.bar));
  const first = row.locator(`.sb-bar[data-bar="${ordered[0]}"]`).first();
  const next = row.locator(`.sb-bar[data-bar="${ordered[1]}"]`).first();
  await first.focus();
  await page.keyboard.press('ArrowRight');
  await expect(next).toBeFocused();
  await expect(next).toHaveAccessibleName(new RegExp(await row.locator('.sb-unit b').innerText()));
  await page.keyboard.press('ArrowLeft');
  await expect(first).toBeFocused();
  await page.keyboard.press('ArrowDown');
  await expect(grid.locator(`[data-unit-row="${nextId}"] button.sb-bar[tabindex="0"]`)).toBeFocused();
  const focused = grid.locator('button.sb-bar[tabindex="0"]');
  const target = await focused.evaluate(el => [el.closest('[data-unit-row]').dataset.unitRow, el.dataset.bar]);
  const sameBar = grid.locator(`[data-unit-row="${target[0]}"] .sb-bar[data-bar="${target[1]}"][tabindex="0"]`);
  await page.keyboard.press('Enter');
  await expect(page.getByRole('dialog', { name: /Бронь/ })).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(sameBar).toBeFocused();
  await page.keyboard.press('Tab');
  await expect(grid.locator(':focus')).toHaveCount(0);
});

test('в режиме загрузки полосы не предлагают открыть карточку гостя', async ({ page }) => {
  const grid = await board(page, 'sluzhba');
  await expect(grid.locator('.sb-bar').first()).toBeVisible();
  await expect(grid.locator('.sb-bar').first()).toContainText('занято');
  await expect(grid.locator('button.sb-bar')).toHaveCount(0);
  await expect(grid).toHaveAttribute('tabindex', '0');
});

test('фокус поздней брони оставляет название объекта видимым на телефоне', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const grid = await board(page);
  const bar = grid.locator('button.sb-bar').filter({ hasText: /./ }).first();
  await expect(bar).toBeVisible();
  const late = await grid.evaluate(el => {
    const candidate = [...el.querySelectorAll('button.sb-bar')].find(bar => Number.parseFloat(bar.style.left) > 65);
    if (!candidate) return null;
    return [candidate.closest('[data-unit-row]').dataset.unitRow, candidate.dataset.bar];
  });
  expect(late).not.toBeNull();
  const row = grid.locator(`[data-unit-row="${late[0]}"]`);
  const selected = row.locator(`button.sb-bar[data-bar="${late[1]}"]`).first();
  await selected.focus();
  await expect(selected).toBeFocused();
  await expect.poll(() => grid.evaluate(el => el.scrollLeft)).toBeGreaterThan(0);
  const [gridBox, unitBox, barBox] = await Promise.all([
    grid.boundingBox(), row.locator('.sb-unit').boundingBox(), selected.boundingBox(),
  ]);
  expect(unitBox.x).toBeGreaterThanOrEqual(gridBox.x);
  expect(barBox.x + barBox.width).toBeGreaterThan(unitBox.x + unitBox.width);
  expect(barBox.x).toBeLessThan(gridBox.x + gridBox.width);
});

test('клавиатурный фокус возвращается к открытой брони после медленного запроса', async ({ page }) => {
  const grid = await board(page);
  const opener = grid.locator('button.sb-bar[tabindex="0"]');
  await opener.focus();
  const openerId = await opener.getAttribute('data-bar');
  const unit = await opener.evaluate(el => el.closest('[data-unit-row]').dataset.unitRow);
  const original = grid.locator(`[data-unit-row="${unit}"] button.sb-bar[data-bar="${openerId}"]`).first();
  const arrived = Promise.withResolvers();
  const release = Promise.withResolvers();
  await page.route('**/api/stays/reservations/*/card', async route => {
    arrived.resolve();
    await release.promise;
    await route.continue();
  });

  await page.keyboard.press('Enter');
  await arrived.promise;
  try {
    await page.keyboard.press('ArrowDown');
    await expect(original).not.toBeFocused();
  } finally {
    release.resolve();
  }
  await expect(page.getByRole('dialog', { name: /Бронь/ })).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(original).toBeFocused();
});

for (const [width, height] of [[320, 640], [390, 844]]) {
  test(`при ${width}px стрелки не прячут фокус под панелями шахматки`, async ({ page }) => {
    await page.setViewportSize({ width, height });
    const grid = await board(page);
    const active = grid.locator('button.sb-bar[tabindex="0"]');
    await active.focus();
    for (let i = 0; i < 4; i++) {
      await expect(active).toBeFocused();
      await expect.poll(() => active.evaluate(bar => {
        const rect = bar.getBoundingClientRect();
        const grid = bar.closest('.sb-grid').getBoundingClientRect();
        const unit = bar.closest('[data-unit-row]').querySelector('.sb-unit').getBoundingClientRect();
        const left = Math.max(rect.left, unit.right, grid.left);
        const right = Math.min(rect.right, grid.right);
        return right > left && document.elementFromPoint((left + right) / 2, (rect.top + rect.bottom) / 2)?.closest('.sb-bar') === bar;
      })).toBe(true);
      await page.keyboard.press('ArrowDown');
    }
  });
}

test('пересортировка строк сохраняет выбранную полосу при переиспользовании DOM', async ({ page }) => {
  const grid = await board(page);
  const target = grid.locator('[data-unit-row] button.sb-bar').nth(2);
  await target.focus();
  const identity = await target.evaluate(el => [
    el.closest('[data-unit-row]').dataset.unitRow, el.dataset.bar, el.dataset.start,
  ]);
  await page.locator('#view-stays .sf-toggle').click();
  await page.locator('#view-stays #sb-dir').selectOption('desc');
  const same = grid.locator(`[data-unit-row="${identity[0]}"] button.sb-bar[data-bar="${identity[1]}"][data-start="${identity[2]}"]`).first();
  await expect(same).toHaveAttribute('tabindex', '0');
});
