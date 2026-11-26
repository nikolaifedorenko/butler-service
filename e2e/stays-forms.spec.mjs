/* «Шахматка», формы и «Гости» (шаг 6д-2): форма брони с предпросмотром, справочник гостей, карточка и семейное дерево. */
import { expect, test } from '@playwright/test';
import { login, watchErrors } from './helpers.mjs';

const open = (page, view) => page.evaluate(v => window.navigate(v), view);

test('семейное дерево открывает карточку другого гостя и сохраняет положение холста', async ({ page }) => {
  const errors = watchErrors(page);
  await page.setViewportSize({ width: 390, height: 780 });
  await login(page, 'admin');
  const family = await page.evaluate(async () => {
    const { api } = await import('/static/js/core.js');
    const surname = 'Древовы' + Date.now();
    const guests = {};
    for (const [key, first_name, gender] of [
      ['root', 'Марк', 'm'], ['sister', 'Нина', 'f'], ['half', 'Олег', 'm'], ['step', 'Анна', 'f'],
      ['mother', 'Вера', 'f'], ['father', 'Иван', 'm'], ['former', 'Елена', 'f'], ['partner', 'Ольга', 'f'],
      ['child', 'Данил', 'm'], ['stepFather', 'Пётр', 'm'],
    ]) {
      guests[key] = await api('/api/stays/guests', { method: 'POST', body: { last_name: surname, first_name, gender } });
    }
    for (const [a, b, kind, former] of [
      ['mother', 'root', 'parent'], ['father', 'root', 'parent'],
      ['mother', 'sister', 'parent'], ['father', 'sister', 'parent'],
      ['father', 'half', 'parent'], ['former', 'half', 'parent'], ['mother', 'father', 'spouse', true],
      ['mother', 'stepFather', 'spouse'], ['stepFather', 'step', 'parent'],
      ['root', 'partner', 'partner'], ['root', 'child', 'parent'], ['partner', 'child', 'parent'],
    ]) {
      const url = `/api/stays/guests/${guests[a].id}/links`;
      await api(url, { method: 'POST', body: { guest_id: guests[b].id, kind, former } });
    }
    return { surname, ...Object.fromEntries(Object.entries(guests).map(([key, guest]) => [key, guest.id])) };
  });
  await open(page, 'guests');
  const view = page.locator('#view-guests');
  const q = view.locator('#gl-q');
  const row = view.locator(`[data-gl-row="${family.root}"]`);
  await q.fill(family.surname);
  await expect(q).toBeFocused();
  await expect(row).toBeVisible();
  await row.click();

  const drawer = page.locator('#drawer');
  await expect(drawer).toContainText('История проживаний');
  await expect(page.locator('#app')).toHaveAttribute('inert', '');
  await drawer.getByRole('button', { name: 'Открыть семейное дерево' }).click();
  await expect(page.locator('#app')).not.toHaveAttribute('inert', '');
  const scroll = view.getByRole('region', { name: 'Холст семейного дерева' });
  const node = key => scroll.locator(`[data-family-person="${family[key]}"]`);
  await expect(node('root')).toContainText('Активный гость');
  await expect(node('sister')).toContainText('Родная сестра');
  await expect(node('half')).toContainText('Брат по отцу');
  await expect(node('step')).toContainText('Сводная сестра');
  await expect(scroll.locator('title').filter({ hasText: 'Брак завершён' })).toHaveCount(1);
  await expect(scroll.locator('title').filter({ hasText: 'Марк' }).filter({ hasText: 'Ольга' }).filter({ hasText: 'Данил' })).toHaveCount(1);

  await view.getByRole('button', { name: 'Увеличить масштаб' }).click();
  await node('partner').scrollIntoViewIfNeeded();
  const position = () => scroll.evaluate(el => [el.scrollLeft, el.scrollTop]);
  const before = await position();
  expect(before[0]).toBeGreaterThan(0);
  const profile = scroll.getByRole('button', { name: 'Карточка', exact: true });
  const placement = await node('partner').evaluate(el => el.closest('[data-family-node]').style.cssText);
  await node('partner').click();
  await expect(node('partner')).toHaveAttribute('aria-pressed', 'true');
  await expect(node('root')).toContainText('партнёр');
  expect(await node('partner').evaluate(el => el.closest('[data-family-node]').style.cssText)).toBe(placement);
  await expect(drawer.getByRole('heading')).toHaveCount(0);
  const path = `**/api/stays/guests/${family.partner}/card`;
  let releaseCard;
  const holdCard = new Promise(resolve => { releaseCard = resolve; });
  let markRequested;
  const requestedCard = new Promise(resolve => { markRequested = resolve; });
  await page.route(path, async route => {
    markRequested();
    await holdCard;
    await route.continue();
  }, { times: 1 });
  try {
    await profile.click();
    await requestedCard;
    await page.keyboard.press('Control+k');
    await expect(page.locator('#palette-q')).toBeFocused();
    const response = page.waitForResponse(path);
    releaseCard();
    await (await response).finished();
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    await page.keyboard.press('Escape');
    await expect(page.locator('#palette-backdrop')).toBeHidden();
    await expect(drawer.getByRole('heading')).toHaveCount(0);
    await expect(profile).toBeFocused();
  } finally {
    releaseCard();
  }

  await profile.click();
  await expect(drawer.getByRole('heading', { name: new RegExp(`${family.surname} Ольга`) })).toBeVisible();
  await expect(drawer.locator('#gc-family')).toHaveCount(0);
  await drawer.getByRole('button', { name: 'К дереву' }).click();
  await expect(profile).toBeFocused();
  expect(await position()).toEqual(before);
  await expect(view.getByText('120%', { exact: true })).toBeVisible();

  await profile.click();
  await expect(drawer.getByRole('heading', { name: new RegExp(`${family.surname} Ольга`) })).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(profile).toBeFocused();
  await profile.click();
  const editorButton = drawer.getByRole('button', { name: 'Редактировать связи' });
  await editorButton.click();
  const editor = page.locator('#modal');
  await expect(editor.getByRole('button', { name: 'Закрыть', exact: true })).toBeFocused();
  await editor.locator('[data-ft-add=parent]').click();
  await editor.locator('[data-ft-last]').fill(family.surname);
  await editor.locator('[data-ft-first]').fill('Новый родитель');
  await editor.locator('[data-ft-create]').click();
  await expect(editor.locator('.ft-tree')).toContainText('Новый родитель');
  await page.keyboard.press('Escape');
  await expect(editorButton).toBeFocused();
  await drawer.getByRole('button', { name: 'К дереву' }).click();
  await expect(scroll.getByRole('button', { name: /Новый родитель/ })).toBeAttached();
  await expect(profile).toBeFocused();
  await view.getByRole('button', { name: 'К списку гостей' }).click();
  await expect(q).toHaveValue(family.surname);
  await expect(row).toBeFocused();

  await row.click();
  await drawer.getByRole('button', { name: 'Открыть семейное дерево' }).click();
  await expect(scroll).toBeVisible();
  await open(page, 'today');
  await open(page, 'guests');
  await expect(row).toBeVisible();
  await expect(scroll).toBeHidden();
  expect(errors).toEqual([]);
});

test('карточка из шахматки открывает холст и сохраняет ребёнка с выбранным вторым родителем', async ({ page }) => {
  const errors = watchErrors(page);
  await login(page, 'admin');
  const data = await page.evaluate(async () => {
    const { api } = await import('/static/js/core.js');
    const surname = 'Семья' + Date.now();
    const create = body => api('/api/stays/guests', { method: 'POST', body });
    const origin = await create({ last_name: surname, first_name: 'Марк' });
    const first = await create({ last_name: surname, first_name: 'Ольга', middle_name: 'Петровна',
      phone: '+7 916 123-45-67', birth_date: '1990-02-14' });
    const second = await create({ last_name: surname, first_name: 'Ольга', middle_name: 'Петровна',
      phone: '+7 916 123-45-68', birth_date: '1992-03-16' });
    const child = await create({ last_name: surname, first_name: 'Софья' });
    await api(`/api/stays/guests/${first.id}/links`, { method: 'POST', body: { kind: 'parent', guest_id: child.id } });
    return { surname, origin: origin.id, first: first.id, second: second.id, child: child.id };
  });
  await open(page, 'stays');
  const board = page.locator('#view-stays');
  await board.locator('[data-stab=day]').click();
  await board.getByRole('button', { name: 'Найти гостя', exact: true }).click();
  const search = page.getByRole('dialog', { name: 'Найти гостя' });
  await search.locator('#sg-q').fill(data.surname);
  await expect(search.locator(`[data-sg-guest="${data.second}"]`)).toContainText('Ольга Петровна');
  await expect(search.locator(`[data-sg-guest="${data.second}"]`)).toContainText('16.03.1992');
  await search.locator(`[data-sg-guest="${data.origin}"]`).click();
  const drawer = page.locator('#drawer');
  await drawer.getByRole('button', { name: 'Открыть семейное дерево' }).click();
  const tree = page.getByRole('region', { name: 'Холст семейного дерева' });
  await tree.getByRole('button', { name: 'Карточка', exact: true }).click();
  await drawer.getByRole('button', { name: 'Редактировать связи' }).click();
  const editor = page.locator('#modal');
  await editor.locator('[data-ft-add=child]').click();
  await editor.locator('[data-ft-q]').fill(data.surname);
  await editor.locator(`[data-ft-pick="${data.child}"]`).click();
  await expect(editor.locator('.ft-parents')).toContainText('Ольга Петровна');
  await expect(editor.locator('[data-ft-second-q]')).toHaveCount(0);
  await editor.getByRole('button', { name: 'Сохранить с двумя родителями' }).click();
  await expect(editor.locator('.ft-tree')).toContainText('Софья');

  await editor.locator('[data-ft-add=child]').click();
  await editor.locator('[data-ft-child-mode=new]').click();
  await editor.locator('[data-ft-last]').fill(data.surname);
  await editor.locator('[data-ft-first]').fill('Данил');
  await editor.locator('[data-ft-second-q]').fill(data.surname);
  const namesake = editor.locator(`[data-ft-second-pick="${data.second}"]`);
  await expect(namesake).toContainText('+7 916 123-45-68');
  await expect(namesake).toContainText('16.03.1992');
  await namesake.click();
  await editor.getByRole('button', { name: 'Сохранить с двумя родителями' }).click();
  await expect(editor.locator('.ft-tree')).toContainText('Данил');
  const parents = await page.evaluate(async origin => {
    const family = await (await fetch(`/api/stays/guests/${origin}/family`)).json();
    const parents = name => {
      const child = family.people.find(person => person.name.includes(name));
      return family.parents.filter(([id]) => id === child.id).map(([, parent]) => parent).sort();
    };
    return { existing: parents('Софья'), added: parents('Данил') };
  }, data.origin);
  expect(parents.existing).toEqual([data.origin, data.first].sort());
  expect(parents.added).toEqual([data.origin, data.second].sort());

  await page.keyboard.press('Escape');
  await drawer.getByRole('button', { name: 'К дереву' }).click();
  await page.getByRole('button', { name: 'К шахматке' }).click();
  await expect(board).toBeVisible();
  await expect(board.locator('[data-stab=day]')).toHaveAttribute('aria-pressed', 'true');
  await expect(board.locator('#sb-find-guest')).toBeFocused();
  expect(errors).toEqual([]);
});

test('поиск гостя не принимает запоздавший ответ прежнего запроса', async ({ page }) => {
  await login(page, 'admin');
  const guestId = await page.evaluate(async () => {
    const response = await fetch('/api/stays/guests/list?limit=1');
    return (await response.json()).rows[0].id;
  });
  let releaseOld, markOldStarted, markOldServed;
  const oldMayFinish = new Promise(resolve => { releaseOld = resolve; });
  const oldStarted = new Promise(resolve => { markOldStarted = resolve; });
  const oldServed = new Promise(resolve => { markOldServed = resolve; });
  await page.route('**/api/stays/guests?**', async route => {
    const q = new URL(route.request().url()).searchParams.get('q');
    if (q === 'Старый') {
      markOldStarted();
      await oldMayFinish;
      await route.fulfill({ json: [{ id: 910001, short: 'Старый ответ' }] });
      markOldServed();
    } else if (q === 'Новый') {
      await route.fulfill({ json: [{ id: guestId, short: 'Новый ответ' }] });
    } else {
      await route.continue();
    }
  });
  await open(page, 'stays');
  const action = page.locator('#view-stays #sb-find-guest');
  await action.click();
  const lookup = page.getByRole('dialog', { name: 'Найти гостя' });
  const search = lookup.locator('#sg-q');
  const results = lookup.locator('[data-sg-res]');
  await search.fill('Старый');
  try {
    await oldStarted;
    await page.keyboard.press('Escape');
    await action.click();
    await search.fill('Новый');
    await expect(results).toContainText('Новый ответ');
  } finally {
    releaseOld();
  }
  await oldServed;
  await expect(results).toContainText('Новый ответ');
  await expect(results).not.toContainText('Старый ответ');
  await results.getByRole('button', { name: 'Новый ответ' }).click();
  await expect(page.locator('#drawer')).toBeVisible();
  await expect(lookup).toHaveCount(0);
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

test('нижний modal не принимает фокус, а его замена сохраняет порядок возврата', async ({ page }) => {
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
  });
  const drawerClose = page.locator('#drawer .x');
  await expect(drawerClose).toBeFocused();
  await page.evaluate(async () => {
    const { openModal } = await import('/static/js/core.js');
    openModal({ title: 'Второе окно', body: 'Новая версия окна' });
  });
  await page.keyboard.press('Escape');
  await expect(page.locator('#modal-backdrop')).toBeHidden();
  await expect(drawerClose).toBeFocused();
  await page.keyboard.press('Escape');
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

test('холст завершает брак и удаляет связь с выбранным родителем', async ({ page }) => {
  await login(page, 'admin');
  const data = await page.evaluate(async () => {
    const { api } = await import('/static/js/core.js');
    const surname = 'Связие2е' + Date.now();
    const create = (first_name, gender) => api('/api/stays/guests', {
      method: 'POST', body: { last_name: surname, first_name, gender },
    });
    const a = await create('Марк', 'm');
    const b = await create('Анна', 'f');
    const child = await create('Даниил', 'm');
    const differentParent = await create('Ирина', 'f');
    const differentChild = await create('Степан', 'm');
    const matchingChild = await create('Полина', 'f');
    const link = (gid, guest_id, kind) => api(`/api/stays/guests/${gid}/links`, {
      method: 'POST', body: { kind, guest_id },
    });
    const marriage = await link(a.id, b.id, 'spouse');
    await link(a.id, child.id, 'parent');
    await link(b.id, child.id, 'parent');
    await link(differentParent.id, differentChild.id, 'parent');
    await link(b.id, matchingChild.id, 'parent');
    return { surname, origin: a.id, other: b.id, child: child.id, marriage: marriage.id,
      differentChild: differentChild.id, matchingChild: matchingChild.id };
  });
  await open(page, 'guests');
  const view = page.locator('#view-guests');
  await view.locator('#gl-q').fill(data.surname);
  await view.locator(`[data-gl-row="${data.origin}"]`).click();
  await page.locator('#drawer').getByRole('button', { name: 'Открыть семейное дерево' }).click();
  const tree = view.getByRole('region', { name: 'Холст семейного дерева' });
  const child = tree.locator(`[data-family-person="${data.child}"]`);
  const spouse = tree.locator(`[data-family-person="${data.other}"]`);
  await expect(child).toContainText('сын');
  const dialog = page.locator('#modal');
  const addChild = tree.getByRole('button', { name: /^Добавить ребёнка ·/ });
  await addChild.click();
  await expect(dialog.getByRole('heading', { name: 'Добавить общего ребёнка' })).toBeVisible();
  await dialog.locator('[data-ft-q]').fill(data.surname);
  await dialog.locator(`[data-ft-pick="${data.differentChild}"]`).click();
  await expect(dialog.getByText('У ребёнка указан другой родитель. Выберите другого ребёнка или проверьте его связи.')).toBeVisible();
  await expect(dialog.locator('[data-ft-create]')).toBeDisabled();
  await dialog.locator('[data-ft-child-change]').click();
  await dialog.locator('[data-ft-q]').fill(data.surname);
  await dialog.locator(`[data-ft-pick="${data.matchingChild}"]`).click();
  await dialog.getByRole('button', { name: 'Сохранить с двумя родителями' }).click();
  await expect(tree.locator(`[data-family-person="${data.matchingChild}"]`)).toContainText('дочь');
  await addChild.click();
  await dialog.locator('[data-ft-child-mode=new]').click();
  await dialog.locator('[data-ft-last]').fill(data.surname);
  await dialog.locator('[data-ft-first]').fill('Софья');
  await expect(dialog.locator('.ft-parents')).toContainText('Анна');
  await dialog.getByRole('button', { name: 'Сохранить с двумя родителями' }).click();
  await expect(tree.locator('[data-family-person]').filter({ hasText: 'Софья' })).toBeAttached();
  await tree.getByRole('button', { name: /^Добавить связь в ветви.*Даниил/ }).click();
  await expect(dialog.getByRole('button', { name: /Родитель для.*Даниил/ })).toBeVisible();
  await dialog.getByRole('button', { name: 'Ещё ребёнок в этой ветви' }).click();
  await expect(dialog.locator('.ft-parents')).toContainText('Анна');
  await page.keyboard.press('Escape');
  await tree.getByRole('button', { name: /^Изменить брак/ }).click();
  await dialog.getByLabel('Начало брака').fill('2024-05-17');
  await dialog.getByLabel('Брак завершён').check();
  await dialog.getByLabel('Окончание брака').fill('2025-06-20');
  await dialog.getByRole('button', { name: 'Сохранить', exact: true }).click();
  await expect(spouse).toContainText(/бывшая жена|бывшая супруга/);
  await expect(child).toContainText('сын');
  const removeParent = tree.getByRole('button', { name: /^Удалить родительскую связь.*Даниил/ });
  await removeParent.click();
  await dialog.getByLabel(new RegExp(`${data.surname} Марк`)).check();
  let releaseRefresh;
  const held = new Promise(resolve => { releaseRefresh = resolve; });
  let refreshReached;
  const started = new Promise(resolve => { refreshReached = resolve; });
  await page.route(`**/api/stays/guests/${data.origin}/family`, async route => {
    refreshReached();
    await held;
    await route.continue();
  }, { times: 1 });
  try {
    await dialog.getByRole('button', { name: 'Удалить связь', exact: true }).click();
    await expect(dialog).not.toBeVisible();
    await started;
    await spouse.click();
    await expect(child).toContainText('сын');
    await removeParent.click();
    await expect(dialog.getByText(`Родитель · ${data.surname} Анна`, { exact: true })).toBeVisible();
    await page.keyboard.press('Escape');
  } finally { releaseRefresh(); }
  const saved = await page.evaluate(async ({ child, origin }) => {
    const { api } = await import('/static/js/core.js');
    const { parents } = await api(`/api/stays/guests/${child}/family`);
    const { links } = await api(`/api/stays/guests/${origin}/family`);
    return { parents: parents.filter(([id]) => id === child), marriage: links.find(link => link.kind === 'spouse') };
  }, data);
  expect(saved.parents).toEqual([[data.child, data.other]]);
  expect(saved.marriage).toMatchObject({ id: data.marriage, former: true, marriage_start: '2024-05-17', marriage_end: '2025-06-20' });

  await expect(removeParent).toBeFocused();
  await removeParent.click();
  await dialog.getByRole('button', { name: 'Удалить связь', exact: true }).click();
  await expect(child).toHaveCount(0);
  await expect(spouse).toBeFocused();
});
