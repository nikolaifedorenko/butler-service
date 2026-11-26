import { expect, test } from '@playwright/test';
import { login } from './helpers.mjs';

for (const { key, heading } of [
  { key: 'held', heading: 'Ваш кар' },
  { key: 'recommended', heading: 'Рекомендуемый свободный кар' },
  { key: 'charging', heading: 'Доступный кар на зарядке' },
  { key: 'unavailable', heading: 'Свободных каров сейчас нет' },
]) {
  test(`на первом экране электрокаров видно состояние «${heading}»`, async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await login(page, 'gromova');
    await page.route('**/api/cars', async route => {
      const response = await route.fetch();
      const data = await response.json();
      const item = data.cars.find(car => car.status === 'free');
      data.me = {
        held: key === 'held' ? item.id : null,
        free_recommended: key === 'recommended' ? item.id : null,
        assigned: null,
      };
      if (key === 'held') Object.assign(item, { status: 'busy', status_title: 'Занят' });
      if (key === 'unavailable' || key === 'charging') {
        for (const car of data.cars) car.status = 'maintenance';
        if (key === 'charging') Object.assign(item, { status: 'charging', status_title: 'На зарядке' });
      }
      await route.fulfill({ response, json: data });
    });
    await page.evaluate(() => window.navigate('cars'));
    const view = page.locator('#view-cars');
    const work = view.locator('.cars-work-next');
    await expect(work.getByRole('heading', { name: heading })).toBeVisible();
    const [panel, bar] = await Promise.all([work.boundingBox(), page.locator('#tabbar').boundingBox()]);
    expect(panel.y + panel.height).toBeLessThanOrEqual(bar.y);
    expect((await work.boundingBox()).y).toBeLessThan((await view.locator('#cars-q').boundingBox()).y);
    if (key === 'recommended' || key === 'charging') {
      await expect(work.getByRole('button', { name: /Взять №/ })).toBeVisible();
    }
    if (key === 'held') await expect(work.getByRole('button', { name: 'Вернул' })).toBeVisible();
    if (key === 'unavailable') {
      await work.getByRole('button', { name: 'К списку каров' }).click();
      await expect(view.locator('#cars-list')).toBeFocused();
    }
  });
}

test('заряжающийся кар другого сотрудника не становится рекомендацией', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await login(page, 'gromova');
  let expected;
  await page.route('**/api/cars', async route => {
    const response = await route.fetch();
    const data = await response.json();
    for (const car of data.cars) car.status = 'maintenance';
    Object.assign(data.cars[0], { status: 'charging', holder_user_id: 999, holder_name: 'Другой сотрудник' });
    Object.assign(data.cars[1], { status: 'charging', holder_user_id: null, holder_name: null });
    expected = data.cars[1].number;
    data.me = { held: null, free_recommended: null };
    await route.fulfill({ response, json: data });
  });
  await page.evaluate(() => window.navigate('cars'));
  const choice = page.locator('.cars-work-next').getByRole('button', { name: /Взять №/ });
  await expect(choice).toBeVisible();
  await expect(choice).toHaveText(`Взять №${expected}`);
});

test('пользователь с правом взять кар получает рекомендацию даже без профиля сотрудника', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await login(page, 'admin');
  await page.evaluate(() => window.navigate('cars'));
  const choice = page.locator('.cars-work-next');
  await expect(choice.getByRole('heading', { name: 'Рекомендуемый свободный кар' })).toBeVisible();
  await expect(choice.getByRole('button', { name: /Взять №/ })).toBeVisible();
});
