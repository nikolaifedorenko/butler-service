/* Палитра команд (⌘K / Ctrl+K): разделы, действия модулей, живой поиск гостей.
   Открытие/закрытие, навигация клавишами, переход и карточка гостя, Esc только палитру. */
import { expect, test } from '@playwright/test';
import { login, watchErrors } from './helpers.mjs';

const open = page => page.keyboard.press('Control+k');

test('палитра: разделы и действие «Создать бронь», поиск гостя, Esc', async ({ page }) => {
  const errors = watchErrors(page);
  await login(page, 'admin');
  await open(page);
  const box = page.locator('.palette');
  await expect(box.locator('input')).toBeFocused();
  await expect(box.locator('.palette-item').first()).toBeVisible();
  await expect(box.getByText('Создать бронь', { exact: true })).toBeVisible();

  /* стрелки + Enter: переход в раздел */
  await box.locator('input').fill('Шахматка');
  await expect(box.locator('.palette-item').first()).toContainText('Шахматка');
  await page.keyboard.press('Enter');
  await expect.poll(() => page.evaluate(() => window.state.view)).toBe('stays');
  await expect(page.locator('#palette-backdrop')).toBeHidden();

  /* живой поиск гостей — Enter открывает карточку drawer'ом */
  await open(page);
  await box.locator('input').fill('орло');
  await expect(box.locator('.palette-item').first()).toContainText('Орлов', { timeout: 8000 });
  await page.keyboard.press('Enter');
  await expect(page.locator('#drawer')).toContainText('История проживаний', { timeout: 8000 });

  /* Esc закрывает палитру и не трогает drawer под ней */
  await open(page);
  await expect(page.locator('#palette-backdrop')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.locator('#palette-backdrop')).toBeHidden();
  await expect(page.locator('#drawer-backdrop')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.locator('#drawer-backdrop')).toBeHidden();

  /* повторное Ctrl+K — закрывает */
  await open(page);
  await expect(page.locator('#palette-backdrop')).toBeVisible();
  await open(page);
  await expect(page.locator('#palette-backdrop')).toBeHidden();
  expect(errors).toEqual([]);
});

test('палитра поверх modal владеет первым Escape и возвращает фокус', async ({ page }) => {
  await login(page, 'admin');
  await page.evaluate(async () => {
    const core = await import('/static/js/core.js');
    const { html } = await import('/static/js/ui/html.js');
    const opener = document.createElement('button');
    opener.id = 'palette-modal-opener';
    opener.textContent = 'Открыть окно';
    document.body.appendChild(opener);
    opener.focus();
    core.openModal({ title: 'Нижнее окно', body: html`<button id="palette-trigger">Команды</button>` });
  });
  const trigger = page.locator('#palette-trigger');
  await trigger.focus();
  await open(page);
  await expect(page.locator('#palette-backdrop')).toBeVisible();
  await expect(page.locator('#modal-backdrop')).toBeVisible();

  await page.keyboard.press('Escape');
  await expect(page.locator('#palette-backdrop')).toBeHidden();
  await expect(page.locator('#modal-backdrop')).toBeVisible();
  await expect(trigger).toBeFocused();

  await page.keyboard.press('Escape');
  await expect(page.locator('#modal-backdrop')).toBeHidden();
  await expect(page.locator('#palette-modal-opener')).toBeFocused();
});

test('палитра включает Сегодня из полного списка навигации', async ({ page }) => {
  await login(page, 'admin');
  await page.evaluate(() => window.navigate('settings'));
  await expect.poll(() => page.evaluate(() => window.state.view)).toBe('settings');
  await open(page);
  const box = page.locator('.palette');
  await box.locator('input').fill('Сегодня');
  await expect(box.locator('.palette-item')).toHaveCount(1);
  await expect(box.locator('.palette-item')).toContainText('Сегодня');
  await page.keyboard.press('Enter');
  await expect.poll(() => page.evaluate(() => window.state.view)).toBe('today');
});

test('Ctrl+K в Настройках имеет одного владельца и не открывает modal', async ({ page }) => {
  await login(page, 'admin');
  await page.evaluate(() => window.navigate('settings'));
  await expect(page.locator('#view-settings')).toBeVisible();
  await open(page);
  await expect(page.locator('#palette-backdrop')).toBeVisible();
  await expect(page.locator('.palette')).toHaveCount(1);
  await expect(page.locator('#modal-backdrop')).toBeHidden();
  await open(page);
  await page.evaluate(() => document.dispatchEvent(new KeyboardEvent('keydown', {
    key: 'л', code: 'KeyK', ctrlKey: true, bubbles: true, cancelable: true,
  })));
  await expect(page.locator('#palette-backdrop')).toBeVisible();
  await expect(page.locator('#modal-backdrop')).toBeHidden();
});

test('палитра работает без зарегистрированного guest provider', async ({ page }) => {
  await login(page, 'admin');
  await page.evaluate(async () => {
    const registry = await import('/static/js/registry.js');
    window.__guestPaletteProvider = registry.paletteProviders().find(p => p.id === 'guests');
    registry.unregisterPaletteProvider('guests');
  });
  await open(page);
  const box = page.locator('.palette');
  await box.locator('input').fill('Сегодня');
  await expect(box.locator('.palette-item')).toContainText('Сегодня');
  await open(page);
  await page.evaluate(async () => {
    const registry = await import('/static/js/registry.js');
    registry.registerPaletteProvider(window.__guestPaletteProvider);
    delete window.__guestPaletteProvider;
  });
});

test('очистка и переоткрытие не принимают запоздалый поиск provider', async ({ page }) => {
  await login(page, 'admin');
  await page.evaluate(async () => {
    const registry = await import('/static/js/registry.js');
    window.__paletteSignals = [];
    window.__paletteResolvers = [];
    registry.registerPaletteProvider({
      id: 'delayed-test',
      search(_query, signal) {
        window.__paletteSignals.push(signal);
        return new Promise(resolve => window.__paletteResolvers.push(() => resolve([
          { id: 999999, title: 'Запоздалый гость', hint: 'тест' },
        ])));
      },
      activate() {},
    });
  });
  const box = page.locator('.palette');

  await open(page);
  await box.locator('input').fill('задержка один');
  await expect.poll(() => page.evaluate(() => window.__paletteSignals.length)).toBe(1);
  await box.locator('input').fill('');
  await expect.poll(() => page.evaluate(() => window.__paletteSignals[0].aborted)).toBe(true);
  await page.evaluate(() => window.__paletteResolvers.shift()());
  await expect(box.getByText('Запоздалый гость')).toHaveCount(0);

  await box.locator('input').fill('задержка два');
  await expect.poll(() => page.evaluate(() => window.__paletteSignals.length)).toBe(2);
  await open(page);
  await expect.poll(() => page.evaluate(() => window.__paletteSignals[1].aborted)).toBe(true);
  await open(page);
  await page.evaluate(() => window.__paletteResolvers.shift()());
  await expect(box.locator('input')).toHaveValue('');
  await expect(box.getByText('Запоздалый гость')).toHaveCount(0);
  await page.evaluate(async () => {
    const registry = await import('/static/js/registry.js');
    registry.unregisterPaletteProvider('delayed-test');
    delete window.__paletteSignals;
    delete window.__paletteResolvers;
  });
});

test('асинхронная перерисовка palette не забирает фокус у верхнего modal', async ({ page }) => {
  await login(page, 'admin');
  await page.evaluate(async () => {
    const registry = await import('/static/js/registry.js');
    window.__focusProviderSignal = null;
    window.__focusProviderResolve = null;
    registry.registerPaletteProvider({
      id: 'focus-test',
      search(_query, signal) {
        window.__focusProviderSignal = signal;
        return new Promise(resolve => { window.__focusProviderResolve = resolve; });
      },
      activate() {},
    });
  });
  await open(page);
  await page.locator('#palette-q').fill('фокус');
  await page.evaluate(async () => {
    const core = await import('/static/js/core.js');
    const { html } = await import('/static/js/ui/html.js');
    core.openModal({ title: 'Верхнее окно', body: html`<button id="focus-owner">Владелец фокуса</button>` });
    document.getElementById('focus-owner').focus();
  });
  await expect.poll(() => page.evaluate(() => Boolean(window.__focusProviderSignal))).toBe(true);
  await expect(page.locator('#focus-owner')).toBeFocused();
  await page.evaluate(() => window.__focusProviderResolve([{ id: 1, title: 'Результат' }]));
  await expect(page.locator('.palette-item-title').getByText('Результат')).toBeVisible();
  await expect(page.locator('#focus-owner')).toBeFocused();
  await page.evaluate(async () => {
    const registry = await import('/static/js/registry.js');
    registry.unregisterPaletteProvider('focus-test');
  });
});
