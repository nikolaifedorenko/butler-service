import { expect, test } from '@playwright/test';
import { DEMO_PASSWORD, login } from './helpers.mjs';

test.use({ serviceWorkers: 'block' });

const eventKey = 'butler.auth-context.v1';
const frames = page => page.locator('iframe[title^="Fixture"]');
const stored = page => page.evaluate(key => localStorage.getItem(key), eventKey);
const serverContext = async page => {
  const response = await page.request.get('/api/auth/context');
  expect(response.ok()).toBe(true);
  return (await response.json()).auth_context;
};

async function twoPages(page, context) {
  await login(page, 'admin');
  const initial = await stored(page);
  const peer = await context.newPage();
  await peer.goto('/');
  await expect(peer.locator('#view-today.active')).toBeVisible();
  expect(await stored(peer)).toBe(initial);
  return peer;
}

// Hold only a synthetic print document. Cookie changes, /me and /context use the demo server.
async function fixturePrints(page, header) {
  const held = Promise.withResolvers();
  const release = Promise.withResolvers();
  await page.route('**/api/docs/print', async route => {
    if (route.request().postDataJSON().title === 'Fixture delayed') {
      held.resolve();
      await release.promise;
    }
    await route.fulfill({
      contentType: 'text/html', headers: header ? { 'X-Butler-Auth-Context': header } : {},
      body: '<!doctype html><title>Fixture</title><p>Fixture</p>',
    });
  });
  await page.evaluate(() => {
    window.fixtureMounts = [];
    new MutationObserver(records => {
      for (const r of records) for (const node of r.addedNodes) {
        if (node.tagName === 'IFRAME') window.fixtureMounts.push(node.title);
      }
    }).observe(document.body, { childList: true });
  });
  return { held: held.promise, release: release.resolve };
}

async function print(page, title) {
  await page.evaluate(async title => {
    const { printWindow } = await import('/static/js/modules/docs.js');
    window.fixturePending = printWindow(title, '<p>Fixture</p>');
  }, 'Fixture ' + title);
}

async function mounted(page) {
  await print(page, 'mounted');
  await expect(frames(page)).toHaveCount(1);
}

test('logout in the second tab cancels both mounted and pending prints', async ({ page, context }) => {
  const peer = await twoPages(page, context);
  const gate = await fixturePrints(page, await serverContext(page));
  await mounted(page);
  await page.locator('#change-pass-btn').click();
  await print(page, 'delayed');
  await gate.held;
  try {
    await peer.locator('#logout-btn').click();
    await expect(peer.locator('#login-screen')).toBeVisible();
    await expect(frames(page)).toHaveCount(0);
    await expect(page.locator('#login-screen')).toBeVisible();
    await expect(page.locator('#modal-backdrop')).toBeHidden();
    expect(JSON.parse(await stored(peer))).toEqual({ context: null, eventId: expect.any(String) });
    // The request must settle even while the response is withheld.
    await page.evaluate(() => window.fixturePending);
  } finally { gate.release(); }
  expect(await page.evaluate(() => window.fixtureMounts)).toEqual(['Fixture mounted']);
});

test('impersonation start and stop clean frames before the peer reloads with its new identity', async ({ page, context }) => {
  const peer = await twoPages(page, context);
  const admin = await page.locator('#user-name').textContent();
  await page.addInitScript(() => {
    window.addEventListener('pagehide', () => {
      sessionStorage.setItem('fixtureFramesAtPagehide', String(document.querySelectorAll('iframe[title^="Fixture"]').length));
    });
  });
  await page.reload();
  await expect(page.locator('#view-today.active')).toBeVisible();
  await peer.evaluate(() => window.navigate('employees'));
  await peer.locator('#view-employees tr[data-card]').filter({ hasText: 'Иванов' }).first().click();
  let before = await serverContext(page);
  for (const action of ['#modal [data-imp]', '#stop-impersonation']) {
    await fixturePrints(page, before);
    await mounted(page);
    await page.evaluate(() => sessionStorage.removeItem('fixtureFramesAtPagehide'));
    await Promise.all([page.waitForEvent('domcontentloaded'), peer.locator(action).click()]);
    expect(await page.evaluate(() => sessionStorage.getItem('fixtureFramesAtPagehide'))).toBe('0');
    await expect(page.locator('#view-today.active')).toBeVisible();
    const after = await serverContext(page);
    expect(after).not.toBe(before);
    expect(JSON.parse(await stored(page))).toEqual({ context: after, eventId: expect.any(String) });
    if (action.includes('data-imp')) await expect(page.locator('#user-name')).toContainText('Иванов');
    else await expect(page.locator('#user-name')).toHaveText(admin);
    before = after;
  }
});

for (const check of ['periodic', 'foreground']) {
  test(`unpublished cookie change rejects a delayed print and clears a mounted print on ${check} validation`, async ({ page, context }) => {
    const peer = await twoPages(page, context);
    const before = await serverContext(page);
    const originalEvent = await stored(peer);
    const gate = await fixturePrints(page, before);
    await page.clock.install();
    await page.clock.pauseAt(new Date(Date.now() + 1000));
    await mounted(page);
    await print(page, 'delayed');
    await gate.held;
    try {
      const login = await peer.request.post('/api/auth/login', { data: { username: 'admin', password: DEMO_PASSWORD } });
      expect(login.ok()).toBe(true);
      expect(await serverContext(peer)).not.toBe(before);
      expect(await stored(peer)).toBe(originalEvent);
    } finally { gate.release(); }
    await page.evaluate(() => window.fixturePending);
    expect(await page.evaluate(() => window.fixtureMounts)).toEqual(['Fixture mounted']);
    if (check === 'periodic') await page.clock.fastForward(30_000);
    else await page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')));
    await expect(frames(page)).toHaveCount(0);
  });
}

test('missing and mismatched print response headers discard the document', async ({ page }) => {
  await login(page, 'admin');
  for (const header of [null, 'different']) {
    await fixturePrints(page, header);
    await print(page, 'wrong header');
    await page.evaluate(() => window.fixturePending);
    await expect(frames(page)).toHaveCount(0);
    expect(await page.evaluate(() => window.fixtureMounts)).toEqual([]);
  }
});

for (const failure of ['401', 'offline']) {
  test(`a mounted document is released when validation reports ${failure}`, async ({ page, context }) => {
    const peer = await twoPages(page, context);
    await fixturePrints(page, await serverContext(page));
    await mounted(page);
    await page.route('**/api/auth/context', route => failure === '401'
      ? route.fulfill({ status: 401, json: { detail: 'Expired' } }) : route.abort('failed'));
    await page.evaluate(() => window.dispatchEvent(new Event('focus')));
    await expect(frames(page)).toHaveCount(0);
    if (failure === '401') await expect(peer.locator('#login-screen')).toBeVisible();
    else await expect(page.locator('#app')).toBeVisible();
  });
}

test('a common API 401 invalidates a peer immediately', async ({ page, context }) => {
  const peer = await twoPages(page, context);
  await fixturePrints(page, await serverContext(page));
  await mounted(page);
  await peer.route('**/api/auth/me', route => route.fulfill({ status: 401, json: { detail: 'Expired' } }));
  await peer.evaluate(async () => {
    const { api } = await import('/static/js/core.js');
    await api('/api/auth/me', { silent: true }).catch(() => {});
  });
  await expect(peer.locator('#login-screen')).toBeVisible();
  await expect(frames(page)).toHaveCount(0);
  await expect(page.locator('#login-screen')).toBeVisible();
});

test('rotating a password publishes the replacement context', async ({ page, context }) => {
  await login(page, 'gromova');
  const peer = await context.newPage();
  await peer.goto('/');
  await expect(peer.locator('#view-today.active')).toBeVisible();
  const before = await serverContext(page);
  await fixturePrints(peer, before);
  await mounted(peer);
  const temporary = 'fixture-password-42';
  await page.locator('#change-pass-btn').click();
  await page.locator('#cp-old').fill(DEMO_PASSWORD);
  await page.locator('#cp-new').fill(temporary);
  await page.locator('#cp-new2').fill(temporary);
  const response = page.waitForResponse('**/api/auth/change-password');
  await page.locator('#modal [data-save]').click();
  expect((await response).ok()).toBe(true);
  try {
    const after = await serverContext(page);
    expect(after).not.toBe(before);
    await expect.poll(async () => JSON.parse(await stored(page))?.context).toBe(after);
    expect(JSON.parse(await stored(page))).toEqual({ context: after, eventId: expect.any(String) });
    await expect(frames(peer)).toHaveCount(0);
  } finally {
    await page.evaluate(async body => {
      const { api } = await import('/static/js/core.js');
      await api('/api/auth/change-password', { method: 'POST', body });
    }, { old_password: temporary, new_password: DEMO_PASSWORD });
  }
});

test('completion, timeout and invalidation release each resource once', async ({ page }) => {
  await login(page, 'admin');
  await fixturePrints(page, await serverContext(page));
  await page.evaluate(() => {
    const timers = new Map(), listeners = [], jobs = new Map();
    const fromPrint = () => new Error().stack.split('\n')[3]?.includes('/modules/docs.js');
    let fallback, removed = 0, aborts = 0;
    for (const kind of ['Timeout', 'Interval']) {
      const set = window['set' + kind], clear = window['clear' + kind];
      window['set' + kind] = function (callback, ms, ...args) {
        const id = set(callback, ms, ...args);
        if (fromPrint()) {
          timers.set(id, kind);
          if (kind === 'Timeout' && ms === 300_000) fallback = callback;
        }
        return id;
      };
      window['clear' + kind] = id => { timers.delete(id); clear(id); };
    }
    const add = EventTarget.prototype.addEventListener, remove = EventTarget.prototype.removeEventListener;
    EventTarget.prototype.addEventListener = function (type, fn, ...opts) {
      if (fromPrint()) listeners.push({ target: this, type, fn });
      return add.call(this, type, fn, ...opts);
    };
    EventTarget.prototype.removeEventListener = function (type, fn, ...opts) {
      const index = listeners.findIndex(item => item.target === this && item.type === type && item.fn === fn);
      if (index !== -1) listeners.splice(index, 1);
      return remove.call(this, type, fn, ...opts);
    };
    const register = Set.prototype.add, unregister = Set.prototype.delete;
    Set.prototype.add = function (value) {
      if (fromPrint()) jobs.set(value, this);
      return register.call(this, value);
    };
    Set.prototype.delete = function (value) {
      if (jobs.get(value) === this) jobs.delete(value);
      return unregister.call(this, value);
    };
    const fetch = window.fetch;
    window.fetch = function (path, init) {
      if (path === '/api/docs/print') init.signal?.addEventListener('abort', () => { aborts++; });
      return fetch(path, init);
    };
    const removeElement = Element.prototype.remove;
    Element.prototype.remove = function () {
      if (this.tagName === 'IFRAME') removed++;
      return removeElement.call(this);
    };
    window.fixtureResources = () => ({
      jobs: jobs.size, timers: timers.size, listeners: listeners.length,
      frames: document.querySelectorAll('iframe[title^="Fixture"]').length, removed, aborts,
    });
    window.fixtureFallback = () => fallback();
  });
  await mounted(page);
  const active = await page.evaluate(() => window.fixtureResources());
  expect(active.jobs).toBe(1);
  expect(active.timers).toBeGreaterThanOrEqual(2);
  expect(active.listeners).toBeGreaterThanOrEqual(2);
  await page.evaluate(async () => {
    const { publishAuthContext } = await import('/static/js/core.js');
    const frame = document.querySelector('iframe[title="Fixture mounted"]');
    window.dispatchEvent(new MessageEvent('message', {
      origin: location.origin, source: frame.contentWindow, data: { butler_print_done: true },
    }));
    window.fixtureFallback();
    publishAuthContext(null);
  });
  const after = await page.evaluate(() => window.fixtureResources());
  expect(after).toEqual({ jobs: 0, timers: 0, listeners: 0, frames: 0, removed: 1, aborts: 1 });
  test.info().annotations.push({ type: 'resources', description: JSON.stringify({ active, after }) });
});

test('old UI cannot start a print while resuming into a different persisted context', async ({ page }) => {
  await login(page, 'admin');
  const reloaded = page.waitForEvent('domcontentloaded');
  const result = await page.evaluate(async key => {
    const { printWindow } = await import('/static/js/modules/docs.js');
    const { subscribeAuthContext } = await import('/static/js/core.js');
    const seen = [], sent = [];
    const unsubscribe = subscribeAuthContext(event => seen.push(event));
    // A resumed document can read the new event before its storage notification arrives.
    localStorage.setItem(key, JSON.stringify({ context: 'fixture-new', eventId: 'fixture-event' }));
    const fetch = window.fetch;
    window.fetch = (path, init) => {
      if (path !== '/api/docs/print') return fetch(path, init);
      sent.push(path);
      return Promise.resolve(new Response('fixture'));
    };
    void printWindow('Fixture resume', '<p>Fixture</p>');
    unsubscribe();
    return { seen, sent };
  }, eventKey);
  expect(result.seen).toEqual([{ context: 'fixture-new', eventId: 'fixture-event', external: true }]);
  expect(result.sent).toEqual([]);
  await reloaded;
  await expect(page.locator('#view-today.active')).toBeVisible();
});

test('the tab switching identity clears its previous screen before loading permissions', async ({ page }) => {
  await login(page, 'admin');
  await page.evaluate(() => window.navigate('employees'));
  await page.locator('#view-employees tr[data-card]').filter({ hasText: 'Иванов' }).first().click();
  const requested = Promise.withResolvers(), release = Promise.withResolvers();
  await page.route('**/api/auth/me', async route => {
    requested.resolve();
    await release.promise;
    await route.continue();
  });
  try {
    await page.locator('#modal [data-imp]').click();
    await requested.promise;
    await expect(page.locator('#modal-backdrop')).toBeHidden();
    await expect(page.locator('#view-employees tr[data-card]')).toHaveCount(0);
    await expect(page.locator('#user-name')).toContainText('Иванов');
  } finally { release.resolve(); }
  await expect(page.locator('#view-me.active')).toBeVisible();
});
