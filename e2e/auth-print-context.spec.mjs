import { expect, test } from '@playwright/test';
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

for (const winner of ['issuer', 'peer cookie', 'peer event']) {
  test(`held password issuer respects the ${winner} after foreground print validation`, async ({ page, context }) => {
    const peer = await twoPages(page, context);
    const initial = await stored(page);
    const before = await serverContext(page);
    await page.evaluate(() => window.navigate('settings'));
    await expect(page.locator('#view-settings.active [data-st]').first()).toBeVisible();
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
        const other = await peer.request.post('/api/auth/login', { data: { username: 'admin', password: DEMO_PASSWORD } });
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
      await expect(page.locator('#app #view-settings.active [data-st]').first()).toBeVisible();
      await expect(frames(peer)).toHaveCount(0);
      expect(publications).toEqual([replacement]);
      expect(navigations).toEqual([]);
    } else {
      await expect.poll(() => navigations.length).toBeGreaterThan(0);
      await expect(page.locator('#view-today.active')).toBeVisible();
      expect(await stored(page)).toBe(expectedEvent);
      expect(publications).toEqual([]);
    }
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

async function exercisePasswordRotation({ page, context, request }, checkpoint = () => {}) {
  await page.clock.install();
  await page.clock.pauseAt(new Date(Date.now() + 1000));
  await login(page, 'gromova');
  const punch = page.locator('#view-today.active #today-punch');
  await expect(punch).toBeVisible();
  const initialAction = await punch.textContent();
  const name = await page.locator('#user-name').textContent();
  const peer = await context.newPage();
  await peer.goto('/');
  await expect(peer.locator('#view-today.active')).toBeVisible();
  const before = await serverContext(page);
  await fixturePrints(peer, before);
  await mounted(peer);
  await page.bringToFront();
  const temporary = 'fixture-password-42';
  await page.locator('#change-pass-btn').click();
  await page.locator('#cp-old').fill(DEMO_PASSWORD);
  await page.locator('#cp-new').fill(temporary);
  await page.locator('#cp-new2').fill(temporary);
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
  // This request fixture has its own cookie jar. Rotation revokes its session too.
  const account = password => request.post('/api/auth/login', { data: { username: 'gromova', password } });
  const cleanupLogin = await account(DEMO_PASSWORD);
  expect(cleanupLogin.status()).toBe(200);
  const employeeId = (await cleanupLogin.json()).user.employee_id;
  expect(employeeId).toBeGreaterThan(0);
  const journal = `/api/punches?employee_id=${employeeId}`;
  const readPunches = async () => {
    const response = await request.get(journal);
    expect(response.status()).toBe(200);
    return response.json();
  };
  const baseline = new Set((await readPunches()).map(punch => punch.id));
  const { cookies } = await request.storageState();
  const headers = { 'X-CSRF-Token': cookies.find(cookie => cookie.name === 'tt_csrf').value };
  try {
    const [response] = await Promise.all([
      page.waitForResponse('**/api/auth/change-password'), page.locator('#modal [data-save]').click(),
    ]);
    expect(response.ok()).toBe(true);
    await checkpoint('submission');
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
  } finally {
    try {
      const cleanupSession = await request.get('/api/auth/context');
      expect([200, 401]).toContain(cleanupSession.status());
      if (cleanupSession.status() === 401) {
        expect((await account(temporary)).status()).toBe(200);
        try {
          // The serial demo scenario exclusively owns this employee's new punches.
          for (const punch of await readPunches()) {
            if (!baseline.has(punch.id)) {
              expect((await request.delete(`/api/punches/${punch.id}`, { headers })).status()).toBe(200);
            }
          }
        } catch (error) { expect.soft(error, 'Restore demo punches').toBeUndefined(); }
        const restored = await request.post('/api/auth/change-password', { headers,
          data: { old_password: temporary, new_password: DEMO_PASSWORD } });
        expect(restored.status()).toBe(200);
      }
    } catch (error) { expect.soft(error, 'Restore demo account').toBeUndefined(); }
  }
}

test('rotating a password publishes the replacement context and keeps Today live', async ({ page, context, request }) => {
  await exercisePasswordRotation({ page, context, request });
});

for (const stop of ['submission', 'punch']) {
  test(`password cleanup survives a closed page immediately after ${stop}`, async ({ page, context, request }) => {
    const account = { username: 'gromova', password: DEMO_PASSWORD };
    const original = await request.post('/api/auth/login', { data: account });
    expect(original.status()).toBe(200);
    const employeeId = (await original.json()).user.employee_id;
    const journal = `/api/punches?employee_id=${employeeId}`;
    const baseline = await (await request.get(journal)).json();
    const failure = new Error(`fixture stopped after ${stop}`);
    await expect(exercisePasswordRotation({ page, context, request }, async phase => {
      if (phase === stop) {
        await page.close();
        throw failure;
      }
    })).rejects.toBe(failure);
    const restored = await request.post('/api/auth/login', { data: account });
    expect(restored.status()).toBe(200);
    expect(await (await request.get(journal)).json()).toEqual(baseline);
  });
}

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
      if (published) await page.evaluate(async after => (await import('/static/js/core.js')).publishAuthContext(after), after);
      const settled = published ? page.evaluate(() => window.fixturePending) : page.waitForEvent('domcontentloaded');
      release.resolve();
      await settled;
      await expect(page.locator('#view-today.active .today-hello')).toBeVisible();
      const latest = await stored(peer);
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
