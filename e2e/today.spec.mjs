/* «Сегодня» (шаг 6в-3): стартовый экран с блоками по правам. */
import { expect, test } from '@playwright/test';
import { login, watchErrors } from './helpers.mjs';

const today = page => page.locator('#view-today');

test('стартовый экран — «Сегодня» и первый пункт меню, приветствие и дата', async ({ page }) => {
  const errors = watchErrors(page);
  await login(page, 'ivanov');
  await expect(page.locator('#view-today.active')).toBeVisible();
  await expect(page.locator('#sidenav .nav-item').first()).toHaveAttribute('data-view', 'today');
  await expect(page.locator('#sidenav .nav-item.active')).toHaveAttribute('data-view', 'today');
  await expect(today(page).locator('.today-hello')).toContainText(/Доброй ночи|Доброе утро|Добрый день|Добрый вечер/);
  await expect(today(page).locator('.today-hello')).toContainText('Иван');
  await expect(today(page).locator('.today-date')).toContainText(/(Понедельник|Вторник|Среда|Четверг|Пятница|Суббота|Воскресенье), \d+ /);
  await expect(today(page)).not.toContainText('Загрузка…');
  expect(errors).toEqual([]);
});

test('батлер: мои брони, «Сейчас важно» и карточки гостей; карточка ведёт в «Мои гости»', async ({ page }) => {
  const errors = watchErrors(page);
  await login(page, 'ivanov');
  const view = today(page);
  await expect(view.locator('[data-stat=mine], [data-stat=in], [data-stat=out]')).toHaveCount(3);
  const mine = Number(await view.locator('[data-stat=mine]').textContent());
  const arrivals = Number(await view.locator('[data-stat=in]').textContent());
  const departures = Number(await view.locator('[data-stat=out]').textContent());
  await expect(view.locator('.today-h').first()).toHaveText('Сейчас важно');
  // карточек столько же, сколько броней (одна из них может быть в «Сейчас важно»)
  expect(await view.locator('.today-card').count()).toBe(mine);
  if (arrivals + departures === 0) await expect(view.locator('[data-empty=important]')).toBeVisible();
  else await expect(view.locator('.today-card.urgent')).toHaveCount(1);
  expect(mine).toBeGreaterThan(0);
  await view.locator('.today-card').first().click();
  await expect(page.locator('#view-mystays.active')).toBeVisible();
  expect(errors).toEqual([]);
});

test('руководитель: присутствие и переход в «Отметки»', async ({ page }) => {
  const errors = watchErrors(page);
  await login(page, 'admin');
  const view = today(page);
  await expect(view.locator('[data-stat=at-work]')).toBeVisible();
  await expect(view.locator('[data-stat=expected]')).toBeVisible();
  await expect(view.locator('[data-stat=late]')).toBeVisible();
  await expect(view.locator('[data-stat=mine]')).toHaveCount(0);        // у администратора нет сотрудника — блока гостей нет
  await view.getByRole('button', { name: /Открыть «Отметки»/ }).click();
  await expect(page.locator('#view-marks.active')).toBeVisible();
  expect(errors).toEqual([]);
});

test('сотрудник: смена и кнопка «Пришёл / Ушёл» работают с экрана «Сегодня»', async ({ page }) => {
  const errors = watchErrors(page);
  await login(page, 'gromova');
  const view = today(page);
  await expect(view.locator('.today-shift')).toBeVisible();
  // кнопка есть и когда смена есть, и когда её нет (тогда часы учтутся как переработка — как в «Моих отметках»)
  const btn = view.locator('#today-punch');
  await expect(btn).toBeVisible();
  const was = (await btn.textContent()).trim();
  await btn.click();
  await expect(view.locator('#today-punch')).not.toHaveText(was);
  if (was === 'Ушёл') {                              // после ухода предлагают описать переработку
    await expect(page.locator('#modal .modal-head h3')).toHaveText('Описание переработки');
    await page.locator('#modal [data-skip]').click();
  }
  expect(errors).toEqual([]);
});

test('на телефоне три показателя в один ряд и шапка без горизонтальной прокрутки', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await login(page, 'ivanov');
  const view = today(page);
  await expect(view.locator('[data-stat=mine]')).toBeVisible();
  const tops = await view.locator('.today-stats').first().locator('.stat').evaluateAll(els => els.map(e => Math.round(e.getBoundingClientRect().top)));
  expect(new Set(tops).size).toBe(1);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test('после стирания раздела снаружи (смена пользователя) экран рисуется заново', async ({ page }) => {
  const errors = watchErrors(page);
  await login(page, 'ivanov');
  await expect(today(page).locator('.today-hello')).toBeVisible();
  await page.evaluate(() => document.querySelectorAll('.view').forEach(v => { v.innerHTML = ''; }));
  await page.evaluate(() => window.navigate('today'));
  await expect(today(page).locator('.today-hello')).toBeVisible();
  expect(errors).toEqual([]);
});
