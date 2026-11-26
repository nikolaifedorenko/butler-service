import { expect, test } from '@playwright/test';
import { login } from './helpers.mjs';

test('карточка гостя показывает годовщину только для действующего брака', async ({ page }) => {
  await login(page, 'admin');
  const { name, guest } = await page.evaluate(async () => {
    const { api } = await import('/static/js/core.js');
    const name = 'Датыбрака' + Date.now();
    const create = first_name => api('/api/stays/guests', { method: 'POST', body: { last_name: name, first_name } });
    const root = await create('Ольга');
    const spouse = await create('Николай');
    const ex = await create('Константин');
    for (const [person, dates] of [[spouse, { marriage_start: '2000-12-08' }],
      [ex, { former: true, marriage_start: '1998-01-16', marriage_end: '1999-05-14' }]]) {
      await api(`/api/stays/guests/${root.id}/links`, { method: 'POST',
        body: { kind: 'spouse', guest_id: person.id, ...dates } });
    }
    return { name, guest: root.id };
  });
  await page.evaluate(() => window.navigate('guests'));
  const view = page.locator('#view-guests');
  await view.locator('#gl-q').fill(name);
  await view.locator(`[data-gl-row="${guest}"]`).click();
  const drawer = page.locator('#drawer');
  await expect(drawer.getByText('Годовщина свадьбы · 8 декабря', { exact: true })).toBeVisible();
  await expect(drawer.getByText('Годовщина свадьбы · 16 января', { exact: true })).toHaveCount(0);
  await expect(drawer.getByText('Окончание · 14.05.1999', { exact: true })).toBeVisible();
});
