import { expect, test } from '@playwright/test';
import { randomUUID } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { DEMO_PASSWORD, login } from './helpers.mjs';

test.use({ serviceWorkers: 'block' });

const eventKey = 'butler.auth-context.v1';
const legacyPrintChild = '/static/js/print-page.js';
const worker = readFileSync(new URL('../static/sw.js', import.meta.url), 'utf8');
const [, releaseStamp] = worker.match(/const VERSION = 'tt-([\w.-]+)'/);
const printChild = `${legacyPrintChild}?v=${releaseStamp}`;
const frames = page => page.locator('iframe[title^="Fixture"]');
const stored = page => page.evaluate(key => localStorage.getItem(key), eventKey);
const serverContext = async page => {
  const response = await page.request.get('/api/auth/context');
  expect(response.ok()).toBe(true);
  return (await response.json()).auth_context;
};

test.describe('service-worker upgrades', () => {
  test.use({ serviceWorkers: 'allow' });

  test('a cached pre-handshake child cannot print before the upgraded parent validates', async ({ page }) => {
    await page.addInitScript(() => {
      if (window !== parent) window.print = () => parent.fixturePrintEvents.push('print');
    });
    await login(page, 'admin');
    await page.waitForFunction(() => navigator.serviceWorker.controller !== null);
    const installedPrintKeys = await page.evaluate(async ({ legacy, upgraded }) => {
      const [shell] = await caches.keys();
      const cache = await caches.open(shell);
      const installed = (await cache.keys()).map(request => new URL(request.url))
        .filter(url => url.pathname === legacy).map(url => url.pathname + url.search);

      // Model the cache during deployment, with only the older child available to the active worker.
      await cache.delete(upgraded);
      await cache.put(legacy, new Response("window.addEventListener('load', () => window.print());", {
        headers: { 'Content-Type': 'application/javascript' },
      }));

      const events = window.fixturePrintEvents = [];
      window.addEventListener('message', event => {
        const frame = document.querySelector('iframe[title="Fixture upgraded child"]');
        if (event.source === frame?.contentWindow && event.origin === location.origin && event.data?.butler_print_ready) {
          events.push('ready');
        }
      });
      const fetch = window.fetch;
      const gate = new Promise(resolve => { window.releaseFixturePrintCheck = resolve; });
      window.fetch = async (url, init) => {
        if (url !== '/api/auth/context' || events.at(-1) !== 'ready') return fetch(url, init);
        events.push('checking');
        await gate;
        const response = await fetch(url, init);
        if (response.ok) events.push('validated');
        return response;
      };
      return installed;
    }, { legacy: legacyPrintChild, upgraded: printChild });

    const script = page.waitForResponse(response => new URL(response.url()).pathname === legacyPrintChild);
    await print(page, 'upgraded child');
    try {
      const response = await script;
      expect(response.fromServiceWorker()).toBe(true);
      expect(response.url()).toBe(new URL(printChild, page.url()).href);
      await page.waitForFunction(() => window.fixturePrintEvents.some(event => event === 'checking' || event === 'print'));
      expect(await page.evaluate(() => window.fixturePrintEvents)).toEqual(['ready', 'checking']);
    } finally { await page.evaluate(() => window.releaseFixturePrintCheck()); }
    await expect.poll(() => page.evaluate(() => window.fixturePrintEvents))
      .toEqual(['ready', 'checking', 'validated', 'print']);
    expect(installedPrintKeys).toEqual([printChild]);
    await frames(page).contentFrame().locator('body').evaluate(() => window.dispatchEvent(new Event('afterprint')));
    await expect(frames(page)).toHaveCount(0);
  });
});

test('child readiness waits for a fresh verdict before native print', async ({ page }) => {
  const script = Promise.withResolvers(), releaseScript = Promise.withResolvers();
  const decision = Promise.withResolvers(), releaseCheck = Promise.withResolvers();
  const printed = Promise.withResolvers();
  await page.exposeFunction('recordPrint', () => { decision.resolve('printed'); printed.resolve(); });
  await page.addInitScript(() => { window.print = () => window.recordPrint(); });
  await login(page, 'admin');
  const id = await serverContext(page);
  await page.route(`**${printChild}`, async route => {
    script.resolve();
    await releaseScript.promise;
    await route.continue();
  });
  await print(page, 'readiness');
  await script.promise;
  await page.route('**/api/auth/context', async route => {
    decision.resolve('validating');
    await releaseCheck.promise;
    await route.fulfill({ json: { auth_context: id } });
  });
  try {
    releaseScript.resolve();
    expect(await decision.promise).toBe('validating');
  } finally { releaseCheck.resolve(); }
  await printed.promise;
  const child = frames(page).contentFrame();
  await child.locator('body').evaluate(() => window.dispatchEvent(new Event('afterprint')));
  await expect(frames(page)).toHaveCount(0);
});

async function fixtureShell(page) {
  await page.goto('/');
  await expect(page.locator('#login-screen')).toBeVisible();
  await page.evaluate(async () => {
    const { adoptAuthContext } = await import('/static/js/core.js');
    document.cookie = 'tt_auth_context=fixture; path=/';
    adoptAuthContext('fixture');
    document.querySelector('#app').classList.remove('hidden');
    document.querySelector('#login-screen').classList.add('hidden');
  });
  await page.route('**/api/auth/context', route => route.fulfill({ json: { auth_context: 'fixture' } }));
}

for (const marker of ['replacement', 'signed-out']) {
  test(`held print child accepts no native invocation after a ${marker} marker`, async ({ page }) => {
    let printed = 0;
    await page.exposeFunction('recordPrint', () => { printed++; });
    await page.addInitScript(() => { window.print = () => window.recordPrint(); });
    await fixtureShell(page);
    await page.route('**/api/docs/print', route => route.fulfill({ contentType: 'text/html',
      headers: { 'X-Butler-Auth-Context': 'fixture' }, body: `<script src="${printChild}" defer></script>` }));
    const requested = Promise.withResolvers(), release = Promise.withResolvers();
    await page.route(`**${printChild}`, async route => {
      requested.resolve();
      await release.promise;
      await route.continue();
    });
    await print(page, 'held child');
    await requested.promise;
    try {
      await expect(frames(page)).toHaveCount(1);
      await page.evaluate(marker => { document.cookie = 'tt_auth_context=' + marker + '; path=/'; }, marker);
    } finally { release.resolve(); }
    await expect(frames(page)).toHaveCount(0);
    await expect(page.locator('#app')).toBeHidden();
    expect(printed).toBe(0);
  });
}

for (const verdict of ['replacement', 'signed-out', 'expired']) {
  test(`unowned request deactivates the shell while reconciling ${verdict}`, async ({ page }) => {
    // No authenticated cookie or application mutation endpoint is used by this transport contract.
    await fixtureShell(page);
    const initial = await stored(page);
    await fixturePrints(page, 'fixture');
    await mounted(page);
    const result = await page.evaluate(async verdict => {
      const { api } = await import('/static/js/core.js');
      const routes = [];
      let finish;
      window.fetch = path => {
        routes.push(path);
        if (path === '/__fixture_request__') return Promise.resolve(new Response('{}'));
        return new Promise(resolve => { finish = resolve; });
      };
      document.cookie = verdict === 'expired' ? 'tt_auth_context=; max-age=0; path=/'
        : 'tt_auth_context=' + verdict + '; path=/';
      const pending = api('/__fixture_request__', { method: 'POST', silent: true }).catch(() => {});
      const snapshot = { hidden: document.querySelector('#app').classList.contains('hidden'),
        frames: document.querySelectorAll('iframe[title="Fixture mounted"]').length, routes: [...routes] };
      finish?.(new Response(JSON.stringify({ auth_context: verdict }), { status: verdict === 'replacement' ? 200 : 401 }));
      await pending;
      return snapshot;
    }, verdict);
    expect(result).toEqual({ hidden: true, frames: 0, routes: ['/api/auth/context'] });
    if (verdict === 'replacement') {
      await expect(page.locator('#login-screen')).toBeVisible(); // reload boots without credentials
      expect(await stored(page)).toBe(initial);
    } else {
      await expect(page.locator('#login-screen')).toBeVisible();
      expect(JSON.parse(await stored(page))).toMatchObject({ context: null });
    }
  });
}

test('Today rebuilds its blocks when the available role data changes', async ({ page }) => {
  await login(page, 'admin');
  const today = page.locator('#view-today');
  await expect(today.locator('[data-stat=at-work]')).toBeVisible();
  // Project empty, non-personal samples in the same browser session.
  await page.route('**/api/punches/status', route => route.fulfill({ json: { on_shift: false } }));
  await page.route('**/api/stays/mine/today', route => route.fulfill({ json: { date: '2026-01-01', reservations: [] } }));
  await page.evaluate(() => {
    window.state.user = { name: 'Fixture', employee_id: 1 };
    window.state.perms = ['stays.mine'];
    window.navigate('today');
  });
  await expect(today.locator('[data-stat=mine]')).toBeVisible();
  const employeeBoard = await today.locator('[data-stat=at-work]').count();
  await page.evaluate(() => {
    window.state.user = { name: 'Fixture', employee_id: null };
    window.state.perms = ['presence.view'];
    window.navigate('today');
  });
  await expect(today.locator('.today-hello')).toBeVisible();
  expect({ employeeBoard, shift: await today.locator('.today-shift').count(),
    mine: await today.locator('[data-stat=mine]').count() }).toEqual({ employeeBoard: 0, shift: 0, mine: 0 });
  await expect(today.locator('[data-stat=at-work]')).toBeVisible();
});

test('a declined child readiness verdict releases the job before native print', async ({ page }) => {
  await page.addInitScript(() => { window.print = () => parent.fixturePrintCalls++; });
  await login(page, 'admin');
  await page.evaluate(() => { window.fixturePrintCalls = 0; });
  const id = await serverContext(page);
  let checks = 0;
  await page.route('**/api/auth/context', route => route.fulfill({ json: { auth_context: ++checks === 1 ? id : 'retired' } }));
  await print(page, 'declined');
  await page.evaluate(() => window.fixturePending);
  await expect(frames(page)).toHaveCount(0);
  expect(await page.evaluate(() => window.fixturePrintCalls)).toBe(0);
});

test('a superseded Today load cannot register a poller', async ({ page }) => {
  await login(page, 'admin');
  await expect(page.locator('#view-today [data-stat=at-work]')).toBeVisible();
  const requested = Promise.withResolvers(), release = Promise.withResolvers();
  await page.route('**/api/presence/board', async route => {
    requested.resolve();
    await release.promise;
    await route.fulfill({ json: { at_work_now: 0, expected_now: 0, yet_to_come: [] } });
  });
  await page.evaluate(async () => {
    const { MODULE_VIEWS } = await import('/static/js/registry.js');
    window.fixtureLoad = MODULE_VIEWS.today();
  });
  await requested.promise;
  await page.evaluate(() => window.navigate('fixture-neutral'));
  release.resolve();
  await page.evaluate(() => window.fixtureLoad);
  expect(await page.evaluate(() => window.state.timers.length)).toBe(0);
});

test('a retired rejection leaves the current mounted job intact', async ({ page }) => {
  await login(page, 'admin');
  const id = await serverContext(page);
  const pending = Promise.withResolvers(), release = Promise.withResolvers();
  await page.route('**/__fixture_timeout__', async route => {
    pending.resolve();
    await release.promise;
    await route.fulfill({ status: 401, json: { detail: 'Fixture' } });
  });
  await page.evaluate(async () => {
    const { api } = await import('/static/js/core.js');
    window.fixtureOldRequest = api('/__fixture_timeout__', { silent: true }).catch(() => {});
  });
  await pending.promise;
  try {
    await page.evaluate(async id => (await import('/static/js/core.js')).publishAuthContext(id), id);
    await fixturePrints(page, id);
    await mounted(page);
  } finally { release.resolve(); }
  await page.evaluate(() => window.fixtureOldRequest);
  expect(await frames(page).count()).toBe(1);
});

async function twoPages(page, context, username = 'admin') {
  await login(page, username);
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
    const checking = Promise.withResolvers(), resume = Promise.withResolvers();
    await page.route('**/api/auth/context', async route => {
      checking.resolve();
      await resume.promise;
      await route.continue();
    });
    try {
      const login = await peer.request.post('/api/auth/login', { data: { username: 'admin', password: DEMO_PASSWORD } });
      expect(login.ok()).toBe(true);
      expect(await serverContext(peer)).not.toBe(before);
      expect(await stored(peer)).toBe(originalEvent);
      if (check === 'periodic') await page.clock.fastForward(5_000);
      else await page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')));
      await checking.promise;
      await expect(frames(page)).toHaveCount(0);
      await page.evaluate(() => window.fixturePending);
      expect(await page.evaluate(() => window.fixtureMounts)).toEqual(['Fixture mounted']);
    } finally { gate.release(); resume.resolve(); }
    await expect(page.locator('#view-today.active .today-hello')).toBeVisible();
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
  await peer.route('**/api/auth/context', route => route.fulfill({ status: 401, json: { detail: 'Expired' } }));
  await peer.evaluate(async () => {
    const { api } = await import('/static/js/core.js');
    await api('/api/auth/me', { silent: true }).catch(() => {});
  });
  await expect(peer.locator('#login-screen')).toBeVisible();
  await expect(frames(page)).toHaveCount(0);
  await expect(page.locator('#login-screen')).toBeVisible();
});

const passwordChange = '/api/auth/change-password';
const fixturePasswordChange = `/__playwright${passwordChange}`;
const temporaryPassword = 'fixture-password-42';
const passwordLogin = (request, username, password = DEMO_PASSWORD) => request.post('/api/auth/login', {
  data: { username, password },
});

const passwordTest = test.extend({
  employee: async ({ playwright, baseURL }, use) => {
    const admin = await playwright.request.newContext({ baseURL });
    let employee;
    try {
      expect((await passwordLogin(admin, 'admin')).status()).toBe(200);
      const username = `password-fixture-${randomUUID()}`;
      const created = await admin.post('/api/employees', { headers: await csrfHeaders(admin),
        data: { full_name: 'Password rotation fixture', username, password: DEMO_PASSWORD } });
      expect(created.status()).toBe(200);
      employee = await created.json();
      expect(employee.username).toBe(username);
      await use({ id: employee.id, username, admin, journal: `/api/punches?employee_id=${employee.id}` });
    } finally {
      try {
        if (employee) {
          const archived = await admin.post(`/api/employees/${employee.id}/delete`, { headers: await csrfHeaders(admin) });
          expect(archived.status()).toBe(200);
          expect(await archived.json()).toMatchObject({ id: employee.id, active: false, deleted: true });
        }
      } finally { await admin.dispose(); }
    }
  },
});

for (const winner of ['issuer', 'peer cookie', 'peer event']) {
  passwordTest(`held password issuer respects the ${winner} after foreground print validation`, async ({
    page, context, employee,
  }) => {
    const peer = await twoPages(page, context, employee.username);
    const initial = await stored(page);
    const before = await serverContext(page);
    await expect(page.locator('#view-today.active')).toBeVisible();
    for (const tab of [peer, page]) {
      await fixturePrints(tab, before);
      await mounted(tab);
    }
    await page.bringToFront();
    const held = Promise.withResolvers(), release = Promise.withResolvers();
    const publications = [], navigations = [];
    await page.exposeFunction('waitForIssuerBody', () => { held.resolve(); return release.promise; });
    await page.exposeFunction('observePublication', value => publications.push(value));
    await page.evaluate(async () => {
      const { subscribeAuthContext } = await import('/static/js/core.js');
      subscribeAuthContext(event => { if (!event.external) void window.observePublication(event.context); });
      const text = Response.prototype.text;
      Response.prototype.text = async function () {
        if (this.url.endsWith('/api/auth/change-password')) await window.waitForIssuerBody();
        return text.call(this);
      };
    });
    page.on('request', request => {
      if (request.isNavigationRequest() && request.frame() === page.mainFrame()) navigations.push(request.url());
    });
    await page.locator('#change-pass-btn').click();
    for (const id of ['old', 'new', 'new2']) await page.locator(`#cp-${id}`).fill(DEMO_PASSWORD);
    await page.locator('#modal [data-save]').click();
    let expectedEvent = initial;
    let replacement;
    try {
      await held.promise;
      replacement = await serverContext(page);
      expect(replacement).not.toBe(before);
      await page.evaluate(() => window.dispatchEvent(new Event('focus')));
      await expect(frames(page)).toHaveCount(0);
      if (winner !== 'issuer') {
        const other = await peer.request.post('/api/auth/login', {
          data: { username: employee.username, password: DEMO_PASSWORD },
        });
        expect(other.ok()).toBe(true);
        const context = (await other.json()).auth_context;
        expect(context).not.toBe(replacement);
        if (winner === 'peer event') {
          await peer.evaluate(async context => (await import('/static/js/core.js')).publishAuthContext(context), context);
          expectedEvent = await stored(peer);
        }
      }
    } finally { release.resolve(); }
    if (winner === 'issuer') {
      await expect.poll(async () => JSON.parse(await stored(page))?.context).toBe(replacement);
      await expect(page.locator('#view-today.active')).toBeVisible();
      await expect(frames(peer)).toHaveCount(0);
      expect(publications).toEqual([replacement]);
      expect(navigations).toEqual([]);
    } else {
      await expect.poll(() => navigations.length).toBeGreaterThan(0);
      await expect(page.locator('#view-today.active')).toBeVisible();
      expect(await stored(page)).toBe(expectedEvent);
      expect(publications).toEqual([]);
    }
    expect((await employee.admin.get('/api/auth/context')).status(),
      'Held issuer must not revoke an unrelated administrator session').toBe(200);
  });
}

test('a suspended generation accepts exactly one matching issuer response', async ({ page }) => {
  await fixtureShell(page);
  const result = await page.evaluate(async () => {
    const { api, authContextIsCurrent, authContextSnapshot, subscribeAuthContext } = await import('/static/js/core.js');
    const started = authContextSnapshot();
    const publications = [];
    subscribeAuthContext(event => publications.push(event.context));
    const responses = [];
    window.fetch = () => new Promise(resolve => responses.push(resolve));
    const send = (path, method) => api(path, { method, silent: true }).then(() => true, () => false);
    const ordinary = send('/__fixture_read__', 'POST');
    const wrongMethod = send('/api/auth/change-password', 'GET');
    const first = send('/api/auth/change-password', 'POST');
    const duplicate = send('/api/auth/change-password', 'POST');
    document.cookie = 'tt_auth_context=next; path=/';
    const current = authContextIsCurrent(started);
    const reply = () => Response.json({ auth_context: 'next' });
    for (const resolve of responses.slice(0, 2)) resolve(reply());
    const rejected = await Promise.all([ordinary, wrongMethod]);
    responses[2](reply());
    const accepted = await first;
    responses[3](reply());
    return { current, rejected, accepted, duplicate: await duplicate, publications };
  });
  expect(result).toEqual({ current: false, rejected: [false, false], accepted: true, duplicate: false, publications: ['next'] });
});

test('a rejected issuer releases its own reconciliation wait', async ({ page }) => {
  await fixtureShell(page);
  for (const path of ['**/api/auth/change-password', '**/api/auth/context']) {
    await page.route(path, route => route.fulfill({ status: 401, json: { detail: 'Fixture' } }));
  }
  await page.evaluate(async () => {
    const { api } = await import('/static/js/core.js');
    void api('/api/auth/change-password', { method: 'POST', silent: true })
      .catch(error => { window.fixtureIssuerError = error.message; });
  });
  await expect(page.locator('#login-screen')).toBeVisible();
  await expect.poll(() => page.evaluate(() => window.fixtureIssuerError)).toBe('Требуется вход');
  expect(JSON.parse(await stored(page))).toMatchObject({ context: null });
});

for (const marker of ['winner', 'different']) {
  test(`a losing issuer ${marker === 'winner' ? 'preserves a matching' : 'reconciles a changed'} winner marker`, async ({ page }) => {
    await fixtureShell(page);
    const result = await page.evaluate(async marker => {
      const { api, subscribeAuthContext, subscribeSessionRejection } = await import('/static/js/core.js');
      const { printWindow } = await import('/static/js/modules/docs.js');
      const publications = [], replies = [];
      let settlingLoser = false, checks = 0;
      subscribeAuthContext(event => publications.push(event.context));
      window.fetch = path => {
        if (path === '/api/docs/print') return Promise.resolve(new Response('<p>Fixture</p>', {
          headers: { 'X-Butler-Auth-Context': 'winner' },
        }));
        if (path === '/api/auth/context') {
          if (!settlingLoser) return Promise.resolve(Response.json({ auth_context: 'winner' }));
          checks++;
          return new Promise(resolve => {
            window.verifyReplacement = () => resolve(Response.json({ auth_context: marker }));
          });
        }
        return new Promise(resolve => replies.push(resolve));
      };
      const send = () => api('/api/auth/change-password', { method: 'POST', silent: true }).then(() => true, () => false);
      const first = send(), second = send();
      document.cookie = 'tt_auth_context=winner; path=/';
      replies[0](Response.json({ auth_context: 'winner' }));
      const won = await first;
      await printWindow('Fixture winner', '<p>Fixture</p>');
      const job = document.querySelector('iframe[title="Fixture winner"]');
      let retired = 0;
      subscribeSessionRejection(() => retired++);
      settlingLoser = true;
      document.cookie = 'tt_auth_context=' + marker + '; path=/';
      replies[1](Response.json({ auth_context: 'different' }));
      return { won, lost: !await second, publications, retired, checks, mounted: Boolean(job), kept: job?.isConnected,
        hidden: document.querySelector('#app').classList.contains('hidden') };
    }, marker);
    const changed = marker !== 'winner';
    expect(result).toEqual({ won: true, lost: true, publications: ['winner'],
      retired: Number(changed), checks: Number(changed), mounted: true, kept: !changed, hidden: changed });
    if (changed) {
      await Promise.all([page.waitForEvent('domcontentloaded'), page.evaluate(() => window.verifyReplacement())]);
      expect(JSON.parse(await stored(page)).context).toBe('winner');
    }
  });
}

for (const verdict of ['live', 'revoked']) {
  test(`a late issuer after logout reconciles a ${verdict} cookie`, async ({ page }) => {
    await fixtureShell(page);
    const result = await page.evaluate(async () => {
      const { api } = await import('/static/js/core.js');
      const replies = [];
      window.fixtureSignedOutChecks = 0;
      window.fetch = path => {
        if (path === '/api/auth/context') {
          window.fixtureSignedOutChecks++;
          return new Promise(resolve => { window.resolveSignedOutCheck = resolve; });
        }
        return new Promise(resolve => replies.push({ path, resolve }));
      };
      const late = api('/api/auth/change-password', { method: 'POST', silent: true }).then(() => true, () => false);
      const logout = api('/api/auth/logout', { method: 'POST', silent: true }).then(() => true, () => false);
      document.cookie = 'tt_auth_context=signed-out; path=/';
      replies.find(reply => reply.path === '/api/auth/logout').resolve(Response.json({ ok: true }));
      const loggedOut = await logout;
      document.cookie = 'tt_auth_context=late; path=/';
      replies.find(reply => reply.path === '/api/auth/change-password')
        .resolve(Response.json({ auth_context: 'late' }));
      return { loggedOut, lateRejected: !await late };
    });
    expect(result).toEqual({ loggedOut: true, lateRejected: true });
    await expect.poll(() => page.evaluate(() => window.fixtureSignedOutChecks)).toBe(1);
    await expect(page.locator('#app')).toBeHidden();
    await expect(page.locator('#login-screen')).toBeVisible();
    expect(JSON.parse(await stored(page))).toMatchObject({ context: null });
    if (verdict === 'live') {
      await Promise.all([
        page.waitForEvent('domcontentloaded'),
        page.evaluate(() => window.resolveSignedOutCheck(Response.json({ auth_context: 'late' }))),
      ]);
      // fixtureShell owns no real server session: the reload is the behavior under test,
      // and the fresh document correctly falls back to login when /me returns 401.
      await expect(page.locator('#login-screen')).toBeVisible();
    } else {
      await page.evaluate(() => window.resolveSignedOutCheck(Response.json({ detail: 'Expired' }, { status: 401 })));
      await expect(page.locator('#login-screen')).toBeVisible();
    }
  });
}

for (const source of ['render', 'template', 'fund']) {
  test(`raw ${source} 401 expires its initiating generation`, async ({ page }) => {
    await login(page, 'admin');
    const before = await serverContext(page);
    await fixturePrints(page, before);
    const target = { render: '**/api/docs/render', template: '**/api/docs/templates?**', fund: '**/api/stays/fund/import' }[source];
    const send = async () => {
      if (source === 'render') {
        await page.route('**/api/schedule/absence-period?**', route => route.fulfill({ json: { doc_type: 'fixture' } }));
        await page.evaluate(async () => {
          const { downloadAbsenceDoc } = await import('/static/js/modules/docs.js');
          void downloadAbsenceDoc(1, '2026-01-01', 'docx');
        });
      } else if (source === 'template') {
        await page.evaluate(async () => (await import('/static/js/modules/dicts.js')).openKindModal({ id: 1, code: 'fixture' }));
        await page.locator('#k-file').setInputFiles({ name: 'fixture.docx', mimeType: 'application/octet-stream', buffer: Buffer.alloc(1) });
      } else {
        if (!await page.locator('#fu-file').count()) {
          await page.evaluate(() => window.navigate('settings'));
          await page.locator('#view-settings [data-st=stays_fund]').click();
          await page.locator('#fund-upload').click();
        }
        await page.locator('#fu-file').setInputFiles({ name: 'fixture.xlsx', mimeType: 'application/octet-stream', buffer: Buffer.alloc(1) });
        await page.locator('#fu-go').click();
      }
    };
    await page.route(target, route => route.fulfill({ status: 422, json: source === 'fund'
      ? { errors: [{ sheet: 'Fixture', row: 1, message: 'original detail' }] } : { detail: 'original detail' } }), { times: 1 });
    await send();
    await expect(page.locator(source === 'fund' ? '#fu-out' : '#toast-host')).toContainText('original detail');
    const release = Promise.withResolvers(), held = Promise.withResolvers();
    await page.route(target, async route => {
      held.resolve();
      await release.promise;
      await route.fulfill({ status: 401, json: { detail: 'Fixture rejection' } });
    });
    await send();
    await held.promise;
    await page.evaluate(async before => (await import('/static/js/core.js')).publishAuthContext(before), before);
    await mounted(page);
    release.resolve();
    await expect(page.locator('#loading')).toBeHidden();
    await expect(frames(page)).toHaveCount(1);
    const verifier = Promise.withResolvers();
    await page.route('**/api/auth/context', async route => {
      await verifier.promise;
      await route.fulfill({ status: 401, json: {} });
    });
    try {
      await send();
      await expect(page.locator('#app')).toBeHidden();
      await expect(frames(page)).toHaveCount(0);
    } finally { verifier.resolve(); }
    await expect(page.locator('#login-screen')).toBeVisible();
  });
}

async function csrfHeaders(request) {
  const { cookies } = await request.storageState();
  return { 'X-CSRF-Token': cookies.find(cookie => cookie.name === 'tt_csrf').value };
}

async function readPunches(request, journal) {
  const response = await request.get(journal);
  expect(response.status()).toBe(200);
  return response.json();
}

async function redirectPasswordFixtureRequest(page) {
  // Closing Chromium can release a paused request. Only the test's independent
  // client can submit a mutation when the browser sends to this fixture URL.
  await page.addInitScript(({ endpoint, fixtureEndpoint }) => {
    const fetch = window.fetch;
    window.fetch = (url, options) => fetch(url === endpoint ? fixtureEndpoint : url, options);
  }, { endpoint: passwordChange, fixtureEndpoint: fixturePasswordChange });
}

async function settlePasswordWrite({ request, playwright, baseURL, employee, issuerDispatch, originalProbe, errors }) {
  const originalSessionIsActive = async () => {
    const response = await request.get('/api/auth/context');
    expect([200, 401], 'Check whether rotation revoked the original session').toContain(response.status());
    return response.ok();
  };
  const probeResult = {};
  try {
    if (issuerDispatch && await originalSessionIsActive()) {
      // Keep the pre-rotation session in request. A new login could race with revocation.
      const probe = await playwright.request.newContext({ baseURL });
      try {
        const original = await passwordLogin(probe, employee.username);
        probeResult.status = original.status();
        expect([200, 401], 'Probe the original password before the issuer settles').toContain(probeResult.status);
      } finally {
        await probe.dispose().catch(error => errors.push(error));
      }
    }
  } catch (error) {
    probeResult.error = error;
    errors.push(error);
  }
  try {
    originalProbe(probeResult);
  } catch (error) {
    errors.push(error);
  }

  // A successful login can predate the commit. Await the request that goes to
  // the server, even if the route has already lost the browser response.
  const { upstreamResponse } = (await issuerDispatch) ?? {};
  try {
    await upstreamResponse;
  } catch (cause) {
    throw new Error('Password change outcome is unknown', { cause });
  }
  return originalSessionIsActive();
}

async function restorePasswordFixture({ request, playwright, baseURL, employee, issuerDispatch, originalProbe, baseline, errors }) {
  if (!await settlePasswordWrite({ request, playwright, baseURL, employee, issuerDispatch, originalProbe, errors })) {
    expect((await passwordLogin(request, employee.username, temporaryPassword)).status(), 'Authenticate the rotated account').toBe(200);
    const restored = await request.post(passwordChange, { headers: await csrfHeaders(request),
      data: { old_password: temporaryPassword, new_password: DEMO_PASSWORD } });
    expect(restored.status(), 'Restore the original password').toBe(200);
  }

  const verified = await playwright.request.newContext({ baseURL });
  try {
    const login = await passwordLogin(verified, employee.username);
    expect(login.status(), 'Verify the original password in a fresh client').toBe(200);
    expect((await login.json()).user.employee_id).toBe(employee.id);
    const headers = await csrfHeaders(employee.admin);
    for (const punch of await readPunches(verified, employee.journal)) {
      if (!baseline.has(punch.id)) {
        expect((await employee.admin.delete(`/api/punches/${punch.id}`, { headers })).status(), 'Restore fixture punches').toBe(200);
      }
    }
  } finally {
    await verified.dispose().catch(error => errors.push(error));
  }
}

async function exercisePasswordRotation({ page, context, request, playwright, baseURL, employee }, {
  checkpoint = () => {}, sendIssuer = send => send(), originalProbe = () => {}, captureBeforeClose = false,
} = {}) {
  if (captureBeforeClose) await redirectPasswordFixtureRequest(page);
  await page.clock.install();
  await page.clock.pauseAt(new Date(Date.now() + 1000));
  await login(page, employee.username);
  expect(await page.evaluate(() => window.state.user), 'Native login owns the fixture employee')
    .toMatchObject({ username: employee.username, employee_id: employee.id });
  const punch = page.locator('#view-today.active #today-punch');
  await expect(punch).toBeVisible();
  const initialAction = await punch.textContent();
  const name = await page.locator('#user-name').textContent();
  const peer = await context.newPage();
  await peer.goto('/');
  await peer.locator('#view-today.active').waitFor();
  const before = await serverContext(page);
  await fixturePrints(peer, before);
  await mounted(peer);
  await page.bringToFront();
  await page.locator('#change-pass-btn').click();
  await page.locator('#cp-old').fill(DEMO_PASSWORD);
  await page.locator('#cp-new').fill(temporaryPassword);
  await page.locator('#cp-new2').fill(temporaryPassword);
  const navigations = [], punches = [], statusReads = [];
  const requests = [];
  const punchStatuses = () => punches.map(response => response.status());
  page.on('framenavigated', frame => { if (frame === page.mainFrame()) navigations.push(frame.url()); });
  page.on('request', request => {
    const path = new URL(request.url()).pathname;
    if (path === '/api/punches' || path === '/api/punches/status') requests.push(`${request.method()} ${path}`);
  });
  page.on('response', response => {
    const path = new URL(response.url()).pathname;
    if (path === '/api/punches' && response.request().method() === 'POST') punches.push(response);
    if (path === '/api/punches/status') statusReads.push(response.status());
  });
  const cleanupLogin = await passwordLogin(request, employee.username);
  expect(cleanupLogin.status()).toBe(200);
  expect((await cleanupLogin.json()).user.employee_id).toBe(employee.id);
  const baseline = new Set((await readPunches(request, employee.journal)).map(punch => punch.id));

  // Only the enclosing test has a deadline. Cutting off the transport earlier would
  // lose the receipt while the server could still be committing this write.
  const issuer = await playwright.request.newContext({ timeout: 0 });
  const upstreamUrl = new URL(passwordChange, baseURL).href;
  const browserUrl = new URL(captureBeforeClose ? fixturePasswordChange : passwordChange, baseURL).href;
  let issuerDispatch;
  let settling = false;
  const errors = [];
  const deliveryErrors = [];
  try {
    await page.route(browserUrl, async route => {
      if (settling || issuerDispatch) return route.abort();
      const dispatch = Promise.withResolvers();
      issuerDispatch = dispatch.promise;
      let canSend = true;
      let response;
      try {
        const outgoing = route.request();
        const method = outgoing.method();
        const headers = await outgoing.allHeaders();
        const data = outgoing.postDataBuffer();
        if (captureBeforeClose) {
          expect(outgoing.url()).toBe(browserUrl);
          expect(method, 'Password change must use POST').toBe('POST');
          expect(outgoing.postDataJSON()).toEqual({ old_password: DEMO_PASSWORD, new_password: temporaryPassword });
          expect(headers['content-type']).toContain('application/json');
          expect(headers.cookie).toContain('tt_session=');
          expect(headers['x-csrf-token']).toBeTruthy();
          expect(headers.cookie).toContain(`tt_csrf=${headers['x-csrf-token']}`);
        }
        response = await sendIssuer(() => {
          if (!canSend) throw new Error('The password fixture can dispatch only one request');
          canSend = false;
          const upstreamResponse = issuer.fetch(upstreamUrl, { method, headers, data, maxRedirects: 0 });
          void upstreamResponse.catch(() => {});
          dispatch.resolve({ upstreamResponse });
          return upstreamResponse;
        });
      } catch (error) {
        deliveryErrors.push(error);
      } finally {
        canSend = false;
        dispatch.resolve({});
      }
      try {
        if (page.isClosed()) return;
        if (response) await route.fulfill({ response });
        else await route.abort();
      } catch (error) {
        if (!page.isClosed()) deliveryErrors.push(error);
      }
    });
    const [response] = await Promise.all([
      page.waitForResponse(browserUrl), page.locator('#modal [data-save]').click(),
    ]);
    expect(response.request().method(), 'Password change must use POST').toBe('POST');
    expect(response.ok()).toBe(true);
    await checkpoint('response');
    const after = await serverContext(page);
    expect(after).not.toBe(before);
    await expect.poll(async () => JSON.parse(await stored(page))?.context).toBe(after);
    expect(JSON.parse(await stored(page))).toEqual({ context: after, eventId: expect.any(String) });
    await expect(frames(peer)).toHaveCount(0);
    await expect(page.locator('#modal-backdrop')).toBeHidden();
    await expect(page.locator('#user-name')).toHaveText(name);
    await expect(punch).toBeVisible();

    const check = expect.configure({ soft: true, timeout: 3000 });
    await punch.click();
    await check.poll(punchStatuses, { message: 'Today punch POST after rotation' }).toEqual([200]);
    await checkpoint('punch');

    const beforeForeground = statusReads.length;
    await page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')));
    await check.poll(() => statusReads.slice(beforeForeground), { message: 'Today status read on foreground' }).toEqual([200]);

    const beforeTick = statusReads.length;
    await page.clock.runFor(30_000);
    await check.poll(() => statusReads.slice(beforeTick), { message: 'Today status read on interval' }).toEqual([200]);

    expect(await page.evaluate(() => window.state.timers.length)).toBe(1);
    expect(navigations).toEqual([]);
    expect(punchStatuses()).toEqual([200]);
    expect(statusReads).toEqual([200, 200, 200]); // Reload, foreground and interval.
    expect(requests).toEqual(['GET /api/punches/status', 'POST /api/punches',
      'GET /api/punches/status', 'GET /api/punches/status']);
    await expect(punch).toHaveText(initialAction === 'Пришёл' ? 'Ушёл' : 'Пришёл');
  } catch (error) {
    errors.push(error);
  }
  settling = true;
  try {
    await restorePasswordFixture({ request, playwright, baseURL, employee, issuerDispatch, originalProbe, baseline, errors });
  } catch (error) {
    errors.push(error);
  }
  for (const error of deliveryErrors) {
    if (!errors.some(failure => failure === error || failure.cause === error)) errors.push(error);
  }
  try {
    await issuer.dispose();
  } catch (error) {
    errors.push(error);
  }
  if (errors.length === 1) throw errors[0];
  if (errors.length) {
    const details = errors.map(error => String(error)).join('\n');
    throw new AggregateError(errors, `Password fixture and cleanup failed\n${details}`, { cause: errors[0] });
  }
}

passwordTest.describe('password rotation fixture', () => {
  passwordTest.describe.configure({ mode: 'serial', retries: 0 });

  passwordTest('rotating a password publishes the replacement context and keeps Today live', async ({ page, context, request, playwright, baseURL, employee }) => {
    await exercisePasswordRotation({ page, context, request, playwright, baseURL, employee });
  });

  passwordTest('password cleanup restores a rotation that commits after its first probe', async ({ page, context, request, playwright, baseURL, employee }) => {
    const baseline = await readPunches(employee.admin, employee.journal);
    const dispatched = Promise.withResolvers(), firstProbe = Promise.withResolvers(), releaseIssuer = Promise.withResolvers();
    let committed;
    const scenario = exercisePasswordRotation({ page, context, request, playwright, baseURL, employee }, {
      captureBeforeClose: true,
      sendIssuer: async send => {
        dispatched.resolve();
        await releaseIssuer.promise;
        const response = await send();
        committed = response.status();
        return response;
      },
      originalProbe: firstProbe.resolve,
    });
    const ended = scenario.then(() => undefined, error => error);
    const waitFor = barrier => Promise.race([barrier.promise, ended.then(error => {
      throw error ?? new Error('Password fixture completed before reaching the barrier');
    })]);
    try {
      await waitFor(dispatched);
      await page.close();
      const { status, error } = await waitFor(firstProbe);
      if (error) throw error;
      expect(status, 'Original password before the held rotation commits').toBe(200);
      releaseIssuer.resolve();
      const failure = await ended;
      expect(failure).not.toBeInstanceOf(AggregateError);
      expect(failure?.message).toMatch(/has been closed/);
      expect(committed, 'Dispatched rotation committed after the original-password probe').toBe(200);
      expect(await readPunches(employee.admin, employee.journal)).toEqual(baseline);
    } finally {
      releaseIssuer.resolve();
      await ended;
    }
  });

  passwordTest('password fixture retains the page closure and independent issuer failure', async ({ page, context, request, playwright, baseURL, employee }) => {
    const baseline = await readPunches(employee.admin, employee.journal);
    const issuerFailure = new Error('Independent fixture request failed');
    await expect(exercisePasswordRotation({ page, context, request, playwright, baseURL, employee }, {
      captureBeforeClose: true,
      sendIssuer: async send => {
        await page.close();
        expect((await send()).status()).toBe(200);
        throw issuerFailure;
      },
    })).rejects.toMatchObject({
      errors: [expect.objectContaining({ message: expect.stringMatching(/has been closed/) }), issuerFailure],
    });
    expect(await readPunches(employee.admin, employee.journal)).toEqual(baseline);
  });

  async function exercisePasswordDeliveryLoss({ page, context, request, playwright, baseURL, employee }, baseline) {
    const releaseWrite = Promise.withResolvers(), started = Promise.withResolvers(), settled = Promise.withResolvers();
    const observingWrite = Promise.withResolvers(), prematureRead = Promise.withResolvers();
    const deliveryError = new Error('Password response delivery failed before commit');
    const upstream = await playwright.request.newContext();
    const sendThroughGate = (url, options) => {
      const response = releaseWrite.promise.then(() => upstream.fetch(url, options));
      void response.then(value => settled.resolve(value.status()), settled.reject);
      started.resolve();
      return {
        then(resolve, reject) {
          observingWrite.resolve('waited for write');
          return response.then(resolve, reject);
        },
        catch(reject) { return response.catch(reject); },
      };
    };
    const gatedPlaywright = { request: { newContext: options => options.baseURL
      ? playwright.request.newContext(options)
      : { fetch: sendThroughGate, dispose: () => {} },
    } };
    let originalObserved = false;
    const checkedRequest = {
      get: (path, options) => {
        if (path === '/api/auth/context' && originalObserved) prematureRead.resolve('checked session before write');
        return request.get(path, options);
      },
      post: (...args) => request.post(...args),
      storageState: () => request.storageState(),
    };
    const outcome = exercisePasswordRotation({ page, context, request: checkedRequest, playwright: gatedPlaywright, baseURL, employee }, {
      captureBeforeClose: true,
      sendIssuer: async send => {
        await page.close();
        void send();
        throw deliveryError;
      },
      originalProbe: ({ status }) => {
        originalObserved = status === 200;
      },
    }).then(() => undefined, error => error);
    const atStage = barrier => Promise.race([barrier, outcome.then(error => {
      throw error ?? new Error('Password fixture completed before the delivery-loss barrier');
    })]);
    try {
      await atStage(started.promise);
      const observed = await atStage(Promise.race([observingWrite.promise, prematureRead.promise]));
      const endedBeforeWrite = observed === 'checked session before write';
      if (endedBeforeWrite) await outcome;
      releaseWrite.resolve();
      const status = await (endedBeforeWrite ? settled.promise : atStage(settled.promise));
      expect(status, 'The browser mutation eventually committed').toBe(200);
      const failure = await outcome;
      const original = await passwordLogin(request, employee.username);
      expect(original.status(), `Original login after cleanup (${observed})`).toBe(200);
      expect(originalObserved).toBe(true);
      expect(failure?.errors).toEqual([expect.objectContaining({ message: expect.stringMatching(/has been closed/) }), deliveryError]);
      expect(await readPunches(employee.admin, employee.journal)).toEqual(baseline);
    } finally {
      releaseWrite.resolve();
      await outcome;
      await upstream.dispose();
    }
  }

  passwordTest('password fixture waits for the write after response delivery fails', async ({ page, context, request, playwright, baseURL, employee }) => {
    const baseline = await readPunches(employee.admin, employee.journal);
    await test.step('Surface a login setup failure before waiting for the write', async () => {
      const setupError = new Error('Password fixture login navigation failed before dispatch');
      const loginAttempted = Promise.withResolvers();
      const failedLoginPage = {
        addInitScript: async () => {},
        clock: { install: async () => {}, pauseAt: async () => {} },
        goto: async () => {
          loginAttempted.resolve();
          throw setupError;
        },
      };
      let observed;
      const deliveryLoss = exercisePasswordDeliveryLoss({ page: failedLoginPage, context, request, playwright, baseURL, employee }, baseline)
        .then(() => { observed = 'unexpected success'; }, error => { observed = error; });
      await Promise.race([loginAttempted.promise, deliveryLoss.then(() => { throw observed; })]);
      await expect.poll(() => observed, { message: 'Setup error reaches the delivery-loss caller', timeout: 2000 }).toBe(setupError);
    });
    await exercisePasswordDeliveryLoss({ page, context, request, playwright, baseURL, employee }, baseline);
  });

  passwordTest('password fixture preserves a wrong browser request method', async ({ page, context, request, playwright, baseURL, employee }) => {
    const baseline = await readPunches(employee.admin, employee.journal);
    await page.addInitScript(path => {
      const fetch = window.fetch;
      window.fetch = (url, options) => url === path ? fetch(url, { ...options, method: 'PUT' }) : fetch(url, options);
    }, passwordChange);
    let upstreamStatus;
    const fixtureFailure = await exercisePasswordRotation({ page, context, request, playwright, baseURL, employee }, {
      checkpoint: () => { throw new Error('Fixture accepted the wrong method'); },
      sendIssuer: async send => {
        const response = await send();
        upstreamStatus = response.status();
        return response;
      },
    }).then(() => undefined, error => error);
    expect(upstreamStatus, 'The normal auth endpoint received the browser PUT').toBe(405);
    expect(fixtureFailure?.message).toContain('Password change must use POST');
    expect(await readPunches(employee.admin, employee.journal)).toEqual(baseline);
  });

  passwordTest('password fixture releases the held write when the first probe fails', async ({ page, context, request, playwright, baseURL, employee }) => {
    const baseline = await readPunches(employee.admin, employee.journal);
    const probeError = new Error('Original session context probe failed');
    const dispatched = Promise.withResolvers(), releaseWrite = Promise.withResolvers();
    let firstContext = true, observedProbe;
    const checkedRequest = {
      get: (path, options) => {
        if (path === '/api/auth/context' && firstContext) {
          firstContext = false;
          throw probeError;
        }
        return request.get(path, options);
      },
      post: (...args) => request.post(...args),
      storageState: () => request.storageState(),
    };
    const outcome = exercisePasswordRotation({ page, context, request: checkedRequest, playwright, baseURL, employee }, {
      captureBeforeClose: true,
      sendIssuer: async send => {
        dispatched.resolve();
        await releaseWrite.promise;
        return send();
      },
      originalProbe: result => { observedProbe = result; },
    }).then(() => undefined, error => error);
    try {
      await Promise.race([dispatched.promise, outcome.then(error => { throw error; })]);
      await page.close();
      await expect.poll(() => observedProbe, { message: 'Probe barrier settled while the write was still held', timeout: 2000 })
        .toMatchObject({ error: probeError });
    } finally {
      releaseWrite.resolve();
      await outcome;
    }
    expect((await outcome)?.errors).toEqual([expect.objectContaining({ message: expect.stringMatching(/has been closed/) }), probeError]);
    expect(await readPunches(employee.admin, employee.journal)).toEqual(baseline);
  });

  for (const stop of ['response', 'punch']) {
    passwordTest(`password cleanup survives a closed page immediately after ${stop}`, async ({ page, context, request, playwright, baseURL, employee }) => {
      const baseline = await readPunches(employee.admin, employee.journal);
      const failure = new Error(`fixture stopped after ${stop}`);
      await expect(exercisePasswordRotation({ page, context, request, playwright, baseURL, employee }, {
        captureBeforeClose: true,
        checkpoint: async phase => {
          if (phase === stop) {
            await page.close();
            throw failure;
          }
        },
      })).rejects.toBe(failure);
      expect(await readPunches(employee.admin, employee.journal)).toEqual(baseline);
    });
  }
});

passwordTest('an unknown password write from the closed Today fixture leaves the seeded login usable', async ({ page, context, request, playwright, browser, baseURL, employee }) => {
  const releaseWrite = Promise.withResolvers();
  const upstream = await playwright.request.newContext({ timeout: 0 });
  const lostReceipt = new Error('The dispatched write lost its receipt');
  let hiddenWrite, firstProbe;
  const lostReceiptClient = {
    fetch(url, options) {
      hiddenWrite = releaseWrite.promise.then(() => upstream.fetch(url, options));
      return Promise.reject(lostReceipt);
    },
    dispose: async () => {},
  };
  const lostPlaywright = { request: { newContext: options => options.baseURL
    ? playwright.request.newContext(options) : lostReceiptClient } };
  try {
    const failure = await exercisePasswordRotation({ page, context, request, playwright: lostPlaywright, baseURL, employee }, {
      captureBeforeClose: true,
      sendIssuer: async send => { await page.close(); return send(); },
      originalProbe: result => { firstProbe = result; },
    }).then(() => undefined, error => error);
    expect(failure?.errors).toEqual([
      expect.objectContaining({ message: expect.stringMatching(/has been closed/) }),
      expect.objectContaining({ message: 'Password change outcome is unknown', cause: lostReceipt }),
    ]);
    expect(firstProbe).toEqual({ status: 200 });
    releaseWrite.resolve();
    expect((await hiddenWrite).status(), 'The hidden write committed after cleanup reported an unknown outcome').toBe(200);
    const rotated = await passwordLogin(request, employee.username, temporaryPassword);
    expect(rotated.status()).toBe(200);
    expect((await rotated.json()).user.employee_id).toBe(employee.id);

    const seeded = await browser.newPage({ baseURL });
    try {
      await login(seeded, 'gromova');
      await expect(seeded.locator('#view-today.active #today-punch')).toBeVisible();
    } finally { await seeded.close(); }
  } finally {
    releaseWrite.resolve();
    try { await hiddenWrite; } finally { await upstream.dispose(); }
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

test.describe('review regressions', () => {
  test('boot keeps the shell inactive until preparation completes', async ({ page }) => {
    const login = await page.request.post('/api/auth/login', { data: { username: 'ivanov', password: DEMO_PASSWORD } });
    expect(login.ok()).toBe(true);
    const preparing = Promise.withResolvers(), release = Promise.withResolvers();
    await page.route('**/api/photos/limits', async route => {
      preparing.resolve();
      await release.promise;
      await route.continue();
    });
    await page.goto('/', { waitUntil: 'domcontentloaded' });
    try {
      await preparing.promise;
      await expect(page.locator('#app')).toBeHidden();
      expect(await page.evaluate(() => ({ active: Boolean(window.state.user), permissions: window.state.perms })))
        .toEqual({ active: false, permissions: [] });
    } finally { release.resolve(); }
    await expect(page.locator('#view-today.active')).toBeVisible();
  });

  test('absence preparation retains the identity of the initiating action', async ({ page }) => {
    await login(page, 'admin');
    const held = Promise.withResolvers(), release = Promise.withResolvers();
    const sent = [];
    await page.route('**/api/schedule/absence-period?**', async route => {
      held.resolve();
      await release.promise;
      await route.fulfill({ json: { employee: { full_name: 'Fixture' }, start: '2026-01-01',
        end: '2026-01-01', days: 1, doc_type: 'vacation_paid' } });
    });
    await page.route('**/api/docs/kinds', route => route.fulfill({ json: { kinds: [], placeholders: {} } }));
    await page.route('**/api/docs/print', route => {
      sent.push('print');
      return route.fulfill({ status: 204 });
    });
    await page.evaluate(async () => {
      const { printAbsenceRequest } = await import('/static/js/modules/docs.js');
      window.state.doc = { vacation: '{full_name}' };
      window.fixturePending = printAbsenceRequest(12345, '2026-01-01');
    });
    await held.promise;
    try {
      await page.evaluate(async () => {
        const { publishAuthContext } = await import('/static/js/core.js');
        publishAuthContext('fixture-replacement');
      });
    } finally { release.resolve(); }
    await page.evaluate(() => window.fixturePending);
    // Allow the network request started by the old unawaited print implementation to be observed.
    await page.request.get('/api/health');
    expect(sent).toEqual([]);
  });

  test('a cookie change during the final validation response prevents mounting', async ({ page, context }) => {
    const peer = await twoPages(page, context);
    const before = await serverContext(page);
    await fixturePrints(page, before);
    const held = Promise.withResolvers(), release = Promise.withResolvers();
    await page.route('**/api/auth/context', async route => {
      held.resolve();
      await release.promise;
      await route.fulfill({ json: { auth_context: before } });
    });
    await print(page, 'final validation');
    await held.promise;
    try {
      const replacement = await peer.request.post('/api/auth/login', { data: { username: 'admin', password: DEMO_PASSWORD } });
      expect(replacement.ok()).toBe(true);
      expect(await serverContext(peer)).not.toBe(before);
    } finally { release.resolve(); }
    await page.evaluate(() => window.fixturePending);
    expect(await page.evaluate(() => window.fixtureMounts)).toEqual([]);
  });

  test('afterprint in the real child releases just its own frame', async ({ page }) => {
    await page.addInitScript(() => { if (window !== window.parent) window.print = () => {}; });
    await login(page, 'admin');
    await print(page, 'first');
    await print(page, 'second');
    await expect(frames(page)).toHaveCount(2);
    for (const title of ['Fixture first', 'Fixture second']) {
      const frame = page.frameLocator(`iframe[title="${title}"]`);
      await expect(frame.locator(`script[src="${printChild}"]`)).toHaveCount(1);
      await frame.locator('body').evaluate(body => body.ownerDocument.defaultView.dispatchEvent(new Event('afterprint')));
      await expect(page.locator(`iframe[title="${title}"]`)).toHaveCount(0);
      if (title === 'Fixture first') await expect(frames(page)).toHaveCount(1);
    }
  });

  for (const published of [false, true]) {
    test(`a delayed 401 preserves the ${published ? 'published' : 'unpublished'} replacement session`, async ({ page, context }) => {
      const peer = await twoPages(page, context);
      const original = await stored(peer);
      await peer.evaluate(() => { window.fixtureInitialPeerDocument = true; });
      const peerNavigations = [];
      peer.on('framenavigated', frame => { if (frame === peer.mainFrame()) peerNavigations.push(frame.url()); });
      const held = Promise.withResolvers(), release = Promise.withResolvers();
      await page.route('**/api/auth/me', async route => {
        held.resolve();
        await release.promise;
        await route.fulfill({ status: 401, json: { detail: 'Fixture' } });
      }, { times: 1 });
      await page.evaluate(async () => {
        const { api } = await import('/static/js/core.js');
        window.fixturePending = api('/api/auth/me', { silent: true }).catch(() => {});
      });
      await held.promise;
      const replacement = await peer.request.post('/api/auth/login', { data: { username: 'admin', password: DEMO_PASSWORD } });
      expect(replacement.ok()).toBe(true);
      const after = (await replacement.json()).auth_context;
      const peerNavigation = published ? peer.waitForEvent('framenavigated', frame => frame === peer.mainFrame()) : null;
      if (published) await page.evaluate(async after => (await import('/static/js/core.js')).publishAuthContext(after), after);
      const settled = published ? page.evaluate(() => window.fixturePending) : page.waitForEvent('domcontentloaded');
      release.resolve();
      await settled;
      await expect(page.locator('#view-today.active .today-hello')).toBeVisible();
      if (peerNavigation) {
        await peerNavigation;
        await peer.locator('#view-today.active .today-hello').waitFor();
      }
      const { latest, firstDocument } = await peer.evaluate(key => ({
        latest: localStorage.getItem(key), firstDocument: Boolean(window.fixtureInitialPeerDocument),
      }), eventKey);
      expect(firstDocument).toBe(!published);
      expect(peerNavigations).toHaveLength(published ? 1 : 0);
      if (published) expect(JSON.parse(latest).context).toBe(after);
      else expect(latest).toBe(original);
      await expect(peer.locator('#app')).toBeVisible();
    });
  }

  test('pending employee card and palette cannot return after logout', async ({ page, context }) => {
    const peer = await twoPages(page, context);
    const held = Promise.withResolvers(), release = Promise.withResolvers();
    await page.route('**/api/employees/12345/history', async route => {
      held.resolve();
      await release.promise;
      await route.fulfill({ json: { positions: [], blocks: [], bank_adjustments: [] } });
    });
    await page.evaluate(async () => {
      window.state.employees = [{ id: 12345, full_name: 'Fixture', active: true }];
      const { openEmployeeCard } = await import('/static/js/modules/employees.js');
      window.fixturePending = openEmployeeCard(12345).catch(() => {});
    });
    await held.promise;
    try {
      await peer.locator('#logout-btn').click();
      await expect(page.locator('#login-screen')).toBeVisible();
    } finally { release.resolve(); }
    await page.evaluate(() => window.fixturePending);
    await page.keyboard.press('Control+k');
    expect(await page.evaluate(() => ({
      modal: !document.querySelector('#modal-backdrop').classList.contains('hidden'),
      palette: !document.querySelector('#palette-backdrop').classList.contains('hidden'),
      permissions: window.state.perms.length, menu: window.state.menu.length, employees: window.state.employees.length,
    }))).toEqual({ modal: false, palette: false, permissions: 0, menu: 0, employees: 0 });
  });

  test('peer deactivates the shell before replacement navigation commits', async ({ page, context }) => {
    const peer = await twoPages(page, context);
    const intercepted = Promise.withResolvers(), release = Promise.withResolvers(), shell = Promise.withResolvers();
    await page.route('**/', async route => { intercepted.resolve(); await release.promise; await route.continue(); });
    await page.exposeFunction('fixtureShell', shell.resolve);
    await page.evaluate(key => {
      window.addEventListener('storage', e => {
        if (e.key === key) window.fixtureShell({ hidden: document.querySelector('#app').classList.contains('hidden'),
          user: !!window.state.user, permissions: window.state.perms.length, employees: window.state.employees.length });
      });
    }, eventKey);
    const loaded = page.waitForEvent('domcontentloaded');
    await peer.evaluate(async () => (await import('/static/js/core.js')).publishAuthContext('fixture-next'));
    let snapshot;
    try { await intercepted.promise; snapshot = await shell.promise; } finally { release.resolve(); }
    await loaded;
    expect(snapshot).toEqual({ hidden: true, user: false, permissions: 0, employees: 0 });
  });

  test('a foreground signal during validation schedules a fresh check', async ({ page }) => {
    await login(page, 'admin');
    const before = await serverContext(page);
    await fixturePrints(page, before);
    await page.clock.install();
    await page.clock.pauseAt(new Date(Date.now() + 1000));
    await mounted(page);
    const held = Promise.withResolvers(), release = Promise.withResolvers();
    const second = Promise.withResolvers(), decline = Promise.withResolvers();
    let checks = 0;
    await page.route('**/api/auth/context', async route => {
      if (++checks === 1) { held.resolve(); await release.promise; }
      else if (checks === 2) { second.resolve(); await decline.promise; }
      else return route.continue(); // independent shell reconciliation
      await route.fulfill({ json: { auth_context: checks === 1 ? before : 'fixture-replaced' } });
    });
    await page.evaluate(() => window.dispatchEvent(new Event('focus')));
    await held.promise;
    await page.evaluate(() => window.dispatchEvent(new Event('focus')));
    release.resolve();
    await second.promise;
    try { await expect(frames(page)).toHaveCount(1); } finally { decline.resolve(); }
    await expect(frames(page)).toHaveCount(0);
  });

  test('a common 401 releases local jobs while checking whether the cookie is still valid', async ({ page, context }) => {
    const peer = await twoPages(page, context);
    const before = await serverContext(page), initial = await stored(peer);
    await fixturePrints(page, before);
    await mounted(page);
    const release = Promise.withResolvers();
    let checks = 0;
    await page.route('**/api/auth/context', async route => {
      checks++;
      await release.promise;
      await route.fulfill({ json: { auth_context: before } });
    });
    await page.route('**/api/auth/me', route => route.fulfill({ status: 401, json: { detail: 'Fixture' } }), { times: 1 });
    await page.evaluate(async () => {
      const { api } = await import('/static/js/core.js');
      window.fixturePending = api('/api/auth/me', { silent: true }).catch(() => {});
    });
    const reloaded = page.waitForEvent('domcontentloaded');
    try {
      await expect(frames(page)).toHaveCount(0);
      expect(await stored(peer)).toBe(initial);
      await expect.poll(() => checks).toBe(1);
    } finally { release.resolve(); }
    await reloaded;
    await expect(page.locator('#view-today.active .today-hello')).toBeVisible();
    expect(await stored(peer)).toBe(initial);
    await expect(peer.locator('#app')).toBeVisible();
  });
});
