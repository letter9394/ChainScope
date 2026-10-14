import { pathToFileURL } from 'node:url';

export const PRODUCTION_URL = 'https://chainscope-web3.onrender.com';

async function get(url, timeoutMs, fetchImpl) {
  const response = await fetchImpl(url, {
    method: 'GET',
    cache: 'no-store',
    redirect: 'manual',
    signal: AbortSignal.timeout(timeoutMs),
    headers: { accept: url.endsWith('/api/health') || url.endsWith('/api/auth/csrf') ? 'application/json' : 'text/html' },
  });
  if (response.status !== 200) throw new Error(`${new URL(url).pathname}: HTTP ${response.status}`);
  return response;
}

export async function checkProduction(baseUrl = PRODUCTION_URL, fetchImpl = fetch) {
  const health = await get(`${baseUrl}/api/health`, 30_000, fetchImpl);
  if (!health.headers.get('content-type')?.includes('application/json')) {
    throw new Error('/api/health: expected JSON');
  }
  if (health.headers.get('x-chainscope-maintenance') === '1') {
    throw new Error('/api/health: maintenance mode is enabled');
  }
  const body = await health.json();
  if (body.status !== 'ok' || body.database !== 'postgresql' ||
      body.checks?.database?.status !== 'ok' || body.background_alerts !== true) {
    throw new Error('/api/health: production, database, or alert scheduler is not healthy');
  }

  const homepage = await get(`${baseUrl}/`, 30_000, fetchImpl);
  if (!homepage.headers.get('content-type')?.includes('text/html')) {
    throw new Error('/: expected HTML');
  }
  const html = await homepage.text();
  if (!html.includes('ChainScope')) throw new Error('/: app marker is missing');

  const auth = await get(`${baseUrl}/api/auth/csrf`, 30_000, fetchImpl);
  if (!auth.headers.get('content-type')?.includes('application/json')) {
    throw new Error('/api/auth/csrf: expected JSON');
  }
  // Do not log the CSRF token or any Set-Cookie header.
  return { status: 'ok', database: 'ok', homepage: 'ok', authEntry: 'ok' };
}

export async function checkWithRetry({
  baseUrl = PRODUCTION_URL,
  fetchImpl = fetch,
  attempts = 5,
  intervalMs = 30_000,
  pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
  onAttempt = () => {},
} = {}) {
  if (!Number.isInteger(attempts) || attempts < 1) throw new Error('attempts must be positive');
  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    try {
      return await checkProduction(baseUrl, fetchImpl);
    } catch (error) {
      onAttempt({ attempt, attempts, reason: error.message });
      if (attempt === attempts) throw error;
      await pause(intervalMs);
    }
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  checkWithRetry({ onAttempt: ({ attempt, attempts, reason }) => {
    console.error(`Smoke check ${attempt}/${attempts}: ${reason}`);
  } }).then(() => {
    console.log('Production smoke check passed: health, homepage, auth entry.');
  }).catch((error) => {
    console.error(`Production smoke check failed: ${error.message}`);
    process.exitCode = 1;
  });
}
