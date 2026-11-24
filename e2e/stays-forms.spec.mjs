/* «Шахматка», формы и «Гости» (шаг 6д-2): форма брони с предпросмотром, справочник гостей, карточка и семейное дерево. */
import { expect, test } from '@playwright/test';
import { login, watchErrors } from './helpers.mjs';

const open = (page, view) => page.evaluate(v => window.navigate(v), view);

test('раздел «Гости»: список, поиск без потери фокуса, карточка гостя с деревом', async ({ page }) => {
  const errors = watchErrors(page);
  await login(page, 'admin');
  await open(page, 'guests');
  const view = page.locator('#view-guests');
  await expect(view.locator('#gl-total')).toContainText('Найдено гостей');
  const rows = view.locator('[data-gl-row]');
  expect(await rows.count()).toBeGreaterThan(0);
  const q = view.locator('#gl-q');
  await q.click();
  await page.keyboard.type('а', { delay: 60 });
  await page.waitForTimeout(700);
  await expect(q).toBeFocused();
  await expect(q).toHaveValue('а');
  await q.fill('');
  await expect(view.locator('#gl-total')).toContainText('Найдено гостей');
  // карточка первого гостя — боковая панель — и семейное дерево (рисуется шаблоном)
  await rows.first().click();
  const drawer = page.locator('#drawer');
  await expect(drawer).toContainText('История проживаний');
  await expect(drawer.locator('.ft-tree')).toBeVisible();
  await expect(drawer.locator('[data-ft-person]').first()).toBeVisible();
  await drawer.locator('[data-ft-add=spouse]').click();
  await expect(drawer.locator('[data-ft-q]')).toBeVisible();
  await drawer.locator('[data-ft-cancel]').click();
  await expect(drawer.locator('[data-ft-q]')).toHaveCount(0);
  expect(errors).toEqual([]);
});

test('поиск гостя не принимает запоздавший ответ прежнего запроса', async ({ page }) => {
  await login(page, 'admin');
  const guestId = await page.evaluate(async () => {
    const response = await fetch('/api/stays/guests/list?limit=1');
    return (await response.json()).rows[0].id;
  });
  let releaseOld;
  let markOldStarted;
  const oldMayFinish = new Promise(resolve => { releaseOld = resolve; });
  const oldStarted = new Promise(resolve => { markOldStarted = resolve; });
  await page.route('**/api/stays/guests?**', async route => {
    const q = new URL(route.request().url()).searchParams.get('q');
    if (q === 'Старый') {
      markOldStarted();
      await oldMayFinish;
      await route.fulfill({ json: [{ id: 910001, short: 'Старый ответ' }] });
    } else if (q === 'Новый') {
      await route.fulfill({ json: [{ id: guestId, short: 'Новый ответ' }] });
    } else {
      await route.continue();
    }
  });
  await open(page, 'stays');
  const search = page.locator('#view-stays #sg-q');
  await search.fill('Старый');
  await oldStarted;
  await page.locator('#view-stays [data-stab=day]').click();
  await search.fill('Новый');
  const result = page.locator('#view-stays [data-sg-res]');
  await expect(result).toContainText('Новый ответ');
  await result.getByRole('button', { name: 'Новый ответ' }).click();
  await expect(result).toBeEmpty();
  releaseOld();
  await page.waitForTimeout(500);
  await expect(result).toBeEmpty();
});

test('форма брони: открывается с кнопкой «Проверить» и закрывается без ошибок', async ({ page }) => {
  const errors = watchErrors(page);
  await login(page, 'admin');
  await open(page, 'stays');
  const view = page.locator('#view-stays');
  await expect(view.locator('.sb-grid')).toBeVisible();
  await view.locator('#sb-new').click();
  const modal = page.locator('#modal');
  await expect(modal.locator('#rf-preview')).toBeVisible();
  await expect(modal.locator('select').first()).toBeVisible();
  await modal.locator('[data-close]').click();
  await expect(modal.locator('#rf-preview')).toHaveCount(0);
  expect(errors).toEqual([]);
});

test('Escape закрывает только верхний drawer и возвращает фокус в modal', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 720 });
  await login(page, 'admin');
  await page.evaluate(async () => {
    const core = await import('/static/js/core.js');
    const { html } = await import('/static/js/ui/html.js');
    const opener = document.createElement('button');
    opener.id = 'overlay-test-opener';
    opener.textContent = 'Открыть проверку';
    document.body.appendChild(opener);
    opener.focus();
    core.openModal({
      title: 'Нижнее окно',
      body: html`<button id="overlay-drawer-trigger">Открыть карточку</button>`,
      onMount(modal) {
        modal.querySelector('#overlay-drawer-trigger').onclick = () => core.openDrawer({
          title: 'Верхняя карточка', body: html`<p>Содержимое карточки</p>`,
        });
      },
    });
  });
  const modalBackdrop = page.locator('#modal-backdrop');
  const drawerBackdrop = page.locator('#drawer-backdrop');
  const trigger = page.locator('#overlay-drawer-trigger');
  await trigger.click();
  await expect(modalBackdrop).toBeVisible();
  await expect(drawerBackdrop).toBeVisible();
  const [modalZ, drawerZ] = await Promise.all([
    modalBackdrop.evaluate(el => Number(getComputedStyle(el).zIndex)),
    drawerBackdrop.evaluate(el => Number(getComputedStyle(el).zIndex)),
  ]);
  expect(drawerZ).toBeGreaterThan(modalZ);
  await expect.poll(async () => {
    const drawerBox = await page.locator('#drawer').boundingBox();
    return drawerBox && [Math.round(drawerBox.x), Math.round(drawerBox.x + drawerBox.width)];
  }).toEqual([0, 390]);

  await page.keyboard.press('Escape');
  await expect(drawerBackdrop).toBeHidden();
  await expect(modalBackdrop).toBeVisible();
  await expect(trigger).toBeFocused();

  await page.keyboard.press('Escape');
  await expect(modalBackdrop).toBeHidden();
  await expect(page.locator('#overlay-test-opener')).toBeFocused();
});

test('удаление нижнего overlay сохраняет fallback возврата фокуса', async ({ page }) => {
  await login(page, 'admin');
  await page.evaluate(async () => {
    const core = await import('/static/js/core.js');
    const { html } = await import('/static/js/ui/html.js');
    const opener = document.createElement('button');
    opener.id = 'overlay-fallback-opener';
    opener.textContent = 'Открыть карточку';
    document.body.appendChild(opener);
    opener.focus();
    core.openDrawer({ title: 'Нижняя карточка', body: html`<button id="overlay-modal-trigger">Окно</button>` });
    const trigger = document.getElementById('overlay-modal-trigger');
    trigger.focus();
    core.openModal({ title: 'Верхнее окно', body: html`<p>Проверка</p>` });
    core.closeDrawer();
  });
  await expect(page.locator('#modal-backdrop')).toBeVisible();
  await expect(page.locator('#drawer-backdrop')).toBeHidden();
  await page.keyboard.press('Escape');
  await expect(page.locator('#modal-backdrop')).toBeHidden();
  await expect(page.locator('#overlay-fallback-opener')).toBeFocused();
});

test('замена нижнего modal возвращает фокус в верхний drawer', async ({ page }) => {
  await login(page, 'admin');
  await page.evaluate(async () => {
    const core = await import('/static/js/core.js');
    const { html } = await import('/static/js/ui/html.js');
    const opener = document.createElement('button');
    opener.id = 'overlay-replace-opener';
    opener.textContent = 'Первое окно';
    document.body.appendChild(opener);
    opener.focus();
    core.openModal({ title: 'Первое окно', body: html`<button id="replace-drawer-trigger">Карточка</button>` });
    const firstTrigger = document.getElementById('replace-drawer-trigger');
    firstTrigger.focus();
    core.openDrawer({ title: 'Карточка', body: html`<button id="replace-modal-trigger">Второе окно</button>` });
    const secondTrigger = document.getElementById('replace-modal-trigger');
    secondTrigger.focus();
    core.openModal({ title: 'Второе окно', body: html`<p>Новая версия окна</p>` });
  });
  const drawerTrigger = page.locator('#replace-modal-trigger');
  await page.keyboard.press('Escape');
  await expect(page.locator('#modal-backdrop')).toBeHidden();
  await expect(page.locator('#drawer-backdrop')).toBeVisible();
  await expect(drawerTrigger).toBeFocused();
  await page.keyboard.press('Escape');
  await expect(page.locator('#drawer-backdrop')).toBeHidden();
  await expect(page.locator('#overlay-replace-opener')).toBeFocused();
});

test('замена нижнего modal с фокусом в нём использует прежний fallback', async ({ page }) => {
  await login(page, 'admin');
  await page.evaluate(async () => {
    const core = await import('/static/js/core.js');
    const { html } = await import('/static/js/ui/html.js');
    const opener = document.createElement('button');
    opener.id = 'overlay-stale-opener';
    opener.textContent = 'Первое окно';
    document.body.appendChild(opener);
    opener.focus();
    core.openModal({ title: 'Первое окно', body: html`<button id="stale-modal-focus">Внутри</button>` });
    core.openDrawer({ title: 'Верхняя карточка', body: html`<p>Карточка</p>` });
    document.getElementById('stale-modal-focus').focus();
    core.openModal({ title: 'Второе окно', body: html`<p>Новая версия окна</p>` });
  });
  await page.keyboard.press('Escape');
  await expect(page.locator('#modal-backdrop')).toBeHidden();
  await expect(page.locator('#overlay-stale-opener')).toBeFocused();
});

test('поиск и выбор справочника гостей сбрасываются при смене пользователя', async ({ page }) => {
  await login(page, 'admin');
  await open(page, 'guests');
  await page.locator('#view-guests #gl-q').fill('телефон прежнего гостя');
  await page.evaluate(async () => {
    const guests = await import('/static/js/modules/stays_guests.js');
    const { resetUserViewState } = await import('/static/js/app.js');
    Object.assign(guests.staysGuests, { picked: [11, 12], special: true });
    resetUserViewState();
  });
  await page.waitForTimeout(500);
  const state = await page.evaluate(async () => ({ ...(await import('/static/js/modules/stays_guests.js')).staysGuests }));
  expect(state).toEqual({ q: '', special: false, stayed_from: '', stayed_to: '', birthday: false,
    sort: 'name', dir: 'asc', picked: [] });
});
