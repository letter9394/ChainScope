import assert from 'node:assert/strict';
import { test } from 'node:test';
import { checkProduction, checkWithRetry } from './check-production-smoke.mjs';

const base = 'https://chainscope-web3.onrender.com';
const health = {
  status: 'ok', database: 'postgresql', background_alerts: true,
  checks: { database: { status: 'ok' } },
};

function mockFetch({ healthStatus = 200, healthBody = health, homeStatus = 200, authStatus = 200 } = {}) {
  return async (url) => {
    if (url === `${base}/api/health`) return new Response(JSON.stringify(healthBody), {
      status: healthStatus, headers: { 'content-type': 'application/json' },
    });
    if (url === `${base}/`) return new Response('<html><title>ChainScope</title></html>', {
      status: homeStatus, headers: { 'content-type': 'text/html' },
    });
    if (url === `${base}/api/auth/csrf`) return new Response('{}', {
      status: authStatus, headers: { 'content-type': 'application/json' },
    });
    throw new Error(`Unexpected URL: ${url}`);
  };
}

test('read-only production probes pass with the expected payload', async () => {
  assert.deepEqual(await checkProduction(base, mockFetch()), {
    status: 'ok', database: 'ok', homepage: 'ok', authEntry: 'ok',
  });
});

test('database failure does not pass because HTTP was 200', async () => {
  await assert.rejects(checkProduction(base, mockFetch({
    healthBody: { ...health, checks: { database: { status: 'error' } } },
  })), /not healthy/);
});

test('blocked homepage is reported as a failed probe', async () => {
  await assert.rejects(checkProduction(base, mockFetch({ homeStatus: 403 })), /\/: HTTP 403/);
});

test('auth entry failure is reported', async () => {
  await assert.rejects(checkProduction(base, mockFetch({ authStatus: 503 })), /auth\/csrf: HTTP 503/);
});

test('cold-start failures are retried without waiting in tests', async () => {
  let calls = 0;
  const fetchImpl = async (url) => {
    if (url === `${base}/api/health` && ++calls === 1) {
      return new Response('', { status: 503 });
    }
    return mockFetch()(url);
  };
  const result = await checkWithRetry({ baseUrl: base, fetchImpl, attempts: 2, pause: async () => {} });
  assert.equal(result.status, 'ok');
  assert.equal(calls, 2);
});
