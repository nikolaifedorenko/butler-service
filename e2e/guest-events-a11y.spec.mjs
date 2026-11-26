import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';
import { login } from './helpers.mjs';

for (const colorScheme of ['light', 'dark']) {
  test('доступность календаря и открытых фильтров, ' + colorScheme, async ({ page }) => {
    await page.emulateMedia({ colorScheme });
    await page.route(url => url.pathname === '/api/stays/guest-events', route => route.fulfill({ json: {
      month: '2026-11-01', today: '2026-11-26', filters: { guest_details: true, vip_codes: [{ id: 4, code: '03' }] },
      events: [{ id: 'birthday:1', date: '2026-11-26', kind: 'birthday', title: 'День рождения',
        people: [{ guest_id: 1, name: 'Орлов И.', status: 'staying', unit: '1-516', vip_code: '03',
          special: true, reservation_id: 1 }] }],
    } }));
    await login(page, 'admin');
    await page.locator('#sidenav').getByRole('button', { name: 'Календарь событий', exact: true }).click();
    const view = page.locator('#view-guestevents');
    await expect(view.getByRole('grid')).toHaveAttribute('aria-busy', 'false');
    const scan = () => new AxeBuilder({ page }).include('#view-guestevents')
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']).analyze();
    expect((await scan()).violations.map(v => [v.id, v.nodes[0].target])).toEqual([]);
    await view.getByText('Фильтры', { exact: true }).click();
    await expect(view.getByLabel('Тип события')).toBeVisible();
    expect((await scan()).violations.map(v => [v.id, v.nodes[0].target])).toEqual([]);
  });
}
