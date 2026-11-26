import { expect, test } from '@playwright/test';
import { login } from './helpers.mjs';

const go = page => page.evaluate(() => window.navigate('mystays'));
const currentCards = async page => (await (await page.request.get('/api/stays/mine/today')).json());
const cardFor = (page, id) => page.locator(`#view-mystays [data-mine-card="${id}"]`);

test('у брони с несколькими гостями одно основное действие, каждое имя открывает свой профиль', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await login(page, 'ivanov');
  const data = await currentCards(page);
  const reservation = data.reservations.find(item => item.guests.length > 1);
  await go(page);
  const card = cardFor(page, reservation.reservation_id);
  const primary = card.getByRole('button', { name: 'Открыть бронь', exact: true });
  await expect(primary).toHaveClass(/btn-primary/);
  await expect(card.getByRole('button', { name: 'Изменить', exact: true })).toHaveCount(0);
  for (const guest of reservation.guests) {
    const name = card.getByRole('button', { name: guest.name, exact: true });
    await name.focus();
    await page.keyboard.press('Enter');
    const profile = page.getByRole('dialog');
    await expect(profile).toContainText('История проживаний');
    await expect(profile.getByRole('heading').first()).toContainText(guest.name.split(' ')[0]);
    await page.keyboard.press('Escape');
    await expect(name).toBeFocused();
  }
  await primary.focus();
  await page.keyboard.press('Enter');
  const booking = page.getByRole('dialog', { name: /Бронь/ });
  await expect(booking).toBeVisible();
  await expect(booking.getByRole('button', { name: 'Изменить', exact: true })).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(primary).toBeFocused();
});

test('просмотр только своих броней открывает краткую карточку без права на редактирование', async ({ page }) => {
  await login(page, 'ivanov');
  const data = await currentCards(page);
  const reservation = data.reservations[0];
  const sharedReads = [];
  page.on('request', request => {
    if (/\/api\/stays\/reservations\/[^/]+\/(card|history)$/.test(request.url())) sharedReads.push(request.url());
  });
  await page.evaluate(() => { window.state.perms = ['stays.mine']; });
  await go(page);
  const action = cardFor(page, reservation.reservation_id).getByRole('button', { name: 'Открыть бронь' });
  await action.click();
  const booking = page.getByRole('dialog', { name: /Бронь/ });
  await expect(booking).toContainText(reservation.guests[0].name);
  await expect(booking.getByRole('button', { name: 'Изменить', exact: true })).toHaveCount(0);
  expect(sharedReads).toEqual([]);
  await page.keyboard.press('Escape');
  await expect(action).toBeFocused();
});

test('после сохранения из брони фокус возвращается к той же карточке списка', async ({ page }) => {
  await login(page, 'ivanov');
  const data = await currentCards(page);
  const reservation = data.reservations[0], id = reservation.reservation_id;
  await page.route('**/api/stays/mine/today', route => route.fulfill({ json: data }));
  await page.route(`**/api/stays/reservations/${id}`, route => {
    if (route.request().method() !== 'PUT') return route.continue();
    reservation.note = route.request().postDataJSON().note;
    return route.fulfill({ json: { ok: true } });
  });
  await go(page);
  const card = cardFor(page, id);
  const action = card.getByRole('button', { name: 'Открыть бронь' });
  await action.click();
  await page.getByRole('dialog', { name: /Бронь/ }).getByRole('button', { name: 'Изменить', exact: true }).click();
  const form = page.locator('#modal');
  await form.locator('#rf-note').fill('Проверено после открытия брони');
  await form.getByRole('button', { name: 'Сохранить', exact: true }).click();
  await expect(card).toContainText('Проверено после открытия брони');
  await expect(action).toBeFocused();
});

async function delayResponse(page, url) {
  let started, release;
  const requested = new Promise(resolve => { started = resolve; });
  const held = new Promise(resolve => { release = resolve; });
  const payload = await (await page.request.get(url)).json();
  await page.route('**' + url, async route => {
    started();
    await held;
    await route.fulfill({ json: payload });
  });
  return { requested, release };
}

test('старый запрос профиля не открывает диалог после возврата к списку', async ({ page }) => {
  await login(page, 'ivanov');
  const reservation = (await currentCards(page)).reservations[0];
  const guest = reservation.guests[0];
  const url = '/api/stays/mine/guests/' + guest.guest_id;
  const delayed = await delayResponse(page, url);
  await go(page);
  const section = page.locator('#view-mystays');
  const name = cardFor(page, reservation.reservation_id).getByRole('button', { name: guest.name, exact: true });
  await name.click();
  await delayed.requested;
  await section.getByRole('button', { name: 'Мой месяц' }).click();
  await section.getByRole('button', { name: 'Сегодня', exact: true }).click();
  await expect(name).toBeVisible();
  const response = page.waitForResponse('**' + url);
  delayed.release();
  await (await response).finished();
  // Wait for the request continuation and the next frame before checking the foreground.
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  await expect(page.getByRole('dialog')).toHaveCount(0);
});

test('запоздалая форма брони оставляет палитру команд на переднем плане', async ({ page }) => {
  await login(page, 'ivanov');
  const reservation = (await currentCards(page)).reservations[0];
  const url = '/api/stays/reservations/' + reservation.reservation_id;
  const delayed = await delayResponse(page, url);
  await go(page);
  await cardFor(page, reservation.reservation_id).getByRole('button', { name: 'Открыть бронь' }).click();
  await page.getByRole('dialog', { name: /Бронь/ }).getByRole('button', { name: 'Изменить', exact: true }).click();
  await delayed.requested;
  await page.keyboard.press('Control+k');
  const palette = page.locator('#palette-backdrop');
  await expect(palette).toBeVisible();
  const response = page.waitForResponse('**' + url);
  delayed.release();
  await (await response).finished();
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  await expect(palette).not.toHaveAttribute('inert');
  await expect(page.locator('#rf-note')).toHaveCount(0);
});
