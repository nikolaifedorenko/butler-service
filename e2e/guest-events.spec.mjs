import { expect, test } from '@playwright/test';
import { login } from './helpers.mjs';

const screen = page => page.locator('#view-guestevents');
const today = '2026-11-26';
const month = '2026-11-01';
const vipCodes = [{ id: 4, code: '03' }, { id: 7, code: '17' }];
const events = [{
  id: 'birthday:1', date: today, kind: 'birthday', title: 'День рождения',
  people: [{ guest_id: 1, name: 'Орлова Анна', status: 'none' }],
}, {
  id: 'wedding:6', date: today, kind: 'wedding', title: 'Годовщина свадьбы',
  people: [
    { guest_id: 2, name: 'Петрова Мария', status: 'staying', unit: '1-515', vip_code: '03', special: true },
    { guest_id: 3, name: 'Петров Иван', status: 'unavailable' },
  ],
}, {
  id: 'special:4', date: '2026-11-27', kind: 'special', title: 'Юбилей',
  people: [{ guest_id: 4, name: 'Иванова Ольга', status: 'tentative' }],
}];

async function stubEvents(page, { details = true } = {}) {
  await page.route(url => url.pathname === '/api/stays/guest-events', route => {
    const query = new URL(route.request().url()).searchParams;
    const requestedMonth = query.get('month') || month;
    const data = requestedMonth === month ? events : [];
    const kind = query.get('kind');
    return route.fulfill({ json: {
      month: requestedMonth, today,
      filters: { guest_details: details, vip_codes: details ? vipCodes : [] },
      events: data.filter(event => !kind || event.kind === kind),
    } });
  });
}

const calendarNav = page => page.locator('#sidenav').getByRole('button', { name: 'Календарь событий', exact: true });
const day = (page, date) => screen(page).locator(`button[data-ge-date="${date}"]`);

test('месяц открывается на сегодня, выбор дня и возврат разделяют две отметки', async ({ page }) => {
  await stubEvents(page);
  await login(page, 'admin');
  await calendarNav(page).click();
  const view = screen(page);
  await expect(view.getByRole('heading', { name: 'Календарь событий' })).toBeVisible();
  await expect(day(page, today)).toHaveAttribute('aria-current', 'date');
  await expect(day(page, today)).toHaveAttribute('aria-pressed', 'true');
  const agenda = view.getByRole('region', { name: 'События дня' });
  await expect(agenda.getByText('Орлова Анна')).toBeVisible();
  await expect(agenda.getByText('Годовщина свадьбы', { exact: true })).toHaveCount(1);
  await expect(agenda.getByText('Проживает · 1-515')).toBeVisible();
  await expect(agenda.getByText('Сведения о брони недоступны')).toBeVisible();
  await expect(agenda.getByText('Брони на эту дату нет')).toBeVisible();

  await day(page, today).focus();
  await page.keyboard.press('ArrowRight');
  await expect(day(page, '2026-11-27')).toBeFocused();
  await expect(day(page, '2026-11-27')).toHaveAttribute('aria-pressed', 'true');
  await expect(day(page, today)).toHaveAttribute('aria-current', 'date');
  await expect(day(page, today)).toHaveAttribute('aria-pressed', 'false');
  await expect(agenda.getByText('Юбилей')).toBeVisible();

  await view.getByRole('button', { name: 'Следующий месяц' }).click();
  await expect(view.locator('#ge-period-label')).toHaveText('Декабрь 2026');
  await expect(agenda.getByText('На эту дату событий нет')).toBeVisible();
  await view.getByRole('button', { name: 'Сегодня', exact: true }).click();
  await expect(day(page, today)).toHaveAttribute('aria-pressed', 'true');
  await expect(agenda.getByText('Орлова Анна')).toBeVisible();
});

test('кнопка «Сегодня» учитывает смену даты объекта в открытом календаре', async ({ page }) => {
  let propertyDate = '2026-11-30';
  await page.route(url => url.pathname === '/api/stays/guest-events', route => {
    const params = new URL(route.request().url()).searchParams;
    return route.fulfill({ json: {
      month: params.get('month') || propertyDate.slice(0, 7) + '-01', today: propertyDate,
      filters: { guest_details: true, vip_codes: [] }, events: [],
    } });
  });
  await login(page, 'admin');
  await calendarNav(page).click();
  await expect(day(page, propertyDate)).toHaveAttribute('aria-current', 'date');
  propertyDate = '2026-12-01';
  await screen(page).getByRole('button', { name: 'Сегодня', exact: true }).click();
  await expect(day(page, propertyDate)).toHaveAttribute('aria-current', 'date');
  await expect(day(page, propertyDate)).toHaveAttribute('aria-pressed', 'true');
});

test('панель фильтров показывает число, отправляет несколько VIP-кодов и позволяет сбросить', async ({ page }) => {
  await stubEvents(page);
  await login(page, 'admin');
  await calendarNav(page).click();
  const view = screen(page);
  const trigger = view.getByText('Фильтры', { exact: true });
  await trigger.click();
  await view.getByLabel('Тип события').selectOption('wedding');
  await view.getByLabel('С подтверждённым проживанием').check();
  await view.getByLabel('03', { exact: true }).check();
  await view.getByLabel('17', { exact: true }).check();
  const applied = page.waitForRequest(req => new URL(req.url()).pathname === '/api/stays/guest-events');
  await view.getByLabel('Особый гость').check();
  const query = new URL((await applied).url()).searchParams;
  expect(query.get('kind')).toBe('wedding');
  expect(query.get('confirmed_only')).toBe('true');
  expect(query.getAll('vip_code_ids')).toEqual(['4', '7']);
  expect(query.get('special')).toBe('true');
  await expect(view.locator('summary')).toHaveText('Фильтры (5)');
  await expect(view.getByRole('region', { name: 'События дня' }).getByText('Орлова Анна')).toHaveCount(0);
  await view.getByRole('button', { name: 'Сбросить' }).click();
  await expect(view.locator('summary')).toHaveText('Фильтры');
  await expect(view.getByRole('region', { name: 'События дня' }).getByText('Орлова Анна')).toBeVisible();
});

test('на узком экране календарь доступен в «Разделах», повестка под сеткой и закрытые поля скрыты', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 760 });
  await stubEvents(page, { details: false });
  await login(page, 'ivanov');
  await page.getByRole('button', { name: 'Разделы', exact: true }).click();
  await page.getByRole('dialog', { name: 'Разделы' }).getByRole('button', { name: 'Календарь событий' }).click();
  const view = screen(page);
  await expect(day(page, today)).toBeVisible();
  await view.getByText('Фильтры', { exact: true }).click();
  await expect(view.getByLabel('Тип события')).toBeVisible();
  await expect(view.getByText('VIP-код', { exact: true })).toHaveCount(0);
  await expect(view.getByLabel('Особый гость')).toHaveCount(0);
  const grid = await view.getByRole('grid', { name: 'Месяц' }).boundingBox();
  const agenda = await view.getByRole('region', { name: 'События дня' }).boundingBox();
  expect(agenda.y).toBeGreaterThan(grid.y + grid.height);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(320);
});

test('у роли загрузки нет раздела и прямой адрес API закрыт', async ({ page }) => {
  await login(page, 'sluzhba');
  await expect(calendarNav(page)).toHaveCount(0);
  expect(await page.evaluate(async () => (await fetch('/api/stays/guest-events')).status)).toBe(403);
});

test('календарь открывает доступную карточку брони и различает прошедшее и будущее проживание', async ({ page }) => {
  await login(page, 'admin');
  const booking = await page.evaluate(async () => {
    const { api, todayISO } = await import('/static/js/core.js');
    const first = todayISO().slice(0, 7) + '-01';
    const end = new Date(first + 'T00:00:00Z');
    end.setUTCMonth(end.getUTCMonth() + 1);
    end.setUTCDate(0);
    const last = end.toISOString().slice(0, 10);
    const result = await api(`/api/stays/bookings?first=${first}&last=${last}&limit=1`);
    return result.rows[0];
  });
  expect(booking.id).toBeTruthy();
  await page.route(url => url.pathname === '/api/stays/guest-events', route => route.fulfill({ json: {
    month, today,
    filters: { guest_details: true, vip_codes: [] },
    events: [
      { ...events[0], date: '2026-11-25', people: [{ guest_id: 1, name: 'Орлова Анна', status: 'staying' }] },
      { ...events[2], people: [{ guest_id: 4, name: 'Иванова Ольга', status: 'staying', unit: '1-515',
        reservation_id: booking.id }] },
    ],
  } }));
  await calendarNav(page).click();
  const agenda = screen(page).getByRole('region', { name: 'События дня' });
  await day(page, '2026-11-25').click();
  await expect(agenda.getByText('Проживал(а)', { exact: true })).toBeVisible();
  await expect(agenda.getByRole('button', { name: 'Открыть бронь' })).toHaveCount(0);
  await day(page, '2026-11-27').click();
  await expect(agenda.getByText('Будет проживать · 1-515')).toBeVisible();
  const trigger = agenda.getByRole('button', { name: 'Открыть бронь гостя Иванова Ольга' });
  await trigger.click();
  const card = page.getByRole('dialog', { name: 'Бронь ' + booking.number, exact: true });
  await expect(card).toBeVisible();
  await card.getByRole('button', { name: 'Закрыть', exact: true }).last().click();
  await expect(trigger).toBeFocused();
});

test('гость без брони появляется в повестке и карточка не перекрывает открывшуюся палитру', async ({ page }) => {
  await login(page, 'admin');
  const guest = await page.evaluate(async () => {
    const { api } = await import('/static/js/core.js');
    const { today } = await api('/api/stays/guest-events');
    const last_name = 'Календарный' + Date.now();
    return api('/api/stays/guests', { method: 'POST',
      body: { last_name, first_name: 'Север', birth_date: '1980' + today.slice(4) } });
  });
  await calendarNav(page).click();
  const trigger = screen(page).getByRole('region', { name: 'События дня' })
    .getByRole('button', { name: guest.last_name + ' С.', exact: true });
  await expect(trigger).toBeVisible();
  const path = '**/api/stays/guests/' + guest.id + '/card';
  let releaseCard;
  const holdCard = new Promise(resolve => { releaseCard = resolve; });
  let markRequested;
  const requestedCard = new Promise(resolve => { markRequested = resolve; });
  await page.route(path, async route => {
    markRequested();
    await holdCard;
    await route.continue();
  }, { times: 1 });

  const drawer = page.locator('#drawer');
  try {
    await trigger.click();
    await requestedCard;
    await page.keyboard.press('Control+k');
    await expect(page.locator('#palette-q')).toBeFocused();
    const response = page.waitForResponse(path);
    releaseCard();
    await (await response).finished();
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    await page.keyboard.press('Escape');
    await expect(drawer).toBeHidden();
    await expect(trigger).toBeFocused();
  } finally {
    releaseCard();
  }
  await trigger.click();
  await expect(drawer.getByRole('heading', { name: guest.last_name + ' ' + guest.first_name })).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(trigger).toBeFocused();
});

test('смена дня отменяет запоздалое открытие карточки даже при возврате на прежний день', async ({ page }) => {
  await login(page, 'admin');
  await stubEvents(page);
  await calendarNav(page).click();
  const trigger = screen(page).getByRole('button', { name: 'Орлова Анна', exact: true });
  const path = '**/api/stays/guests/1/card';
  const requested = Promise.withResolvers();
  const release = Promise.withResolvers();
  await page.route(path, async route => {
    const response = await route.fetch();
    requested.resolve();
    await release.promise;
    await route.fulfill({ response });
  }, { times: 1 });

  await trigger.click();
  await requested.promise;
  try {
    await day(page, '2026-11-27').click();
    await day(page, today).click();
    await expect(trigger).toBeVisible();
    const delivered = page.waitForResponse(path);
    release.resolve();
    await (await delivered).finished();
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    await expect(page.locator('#drawer')).toBeHidden();
  } finally {
    release.resolve();
  }
  await trigger.click();
  await expect(page.locator('#drawer')).toBeVisible();
});

test('клавиатурный переход оставляет выбранный день над нижней панелью', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 410 });
  await login(page, 'admin');
  await stubEvents(page);
  await page.locator('#mobile-sections').click();
  await page.getByRole('button', { name: 'Календарь событий', exact: true }).click();
  await day(page, '2026-11-01').click();
  await page.locator('main.content').evaluate(element => { element.scrollTop = 0; });
  for (let i = 0; i < 3; i++) await page.keyboard.press('ArrowDown');
  const selected = day(page, '2026-11-22');
  await expect(selected).toBeFocused();
  await expect.poll(() => selected.evaluate(element =>
    element.getBoundingClientRect().bottom <= document.querySelector('#tabbar').getBoundingClientRect().top)).toBe(true);
});
