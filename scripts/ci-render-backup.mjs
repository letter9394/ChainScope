import { spawnSync } from 'node:child_process';
import { createCipheriv, createHash, randomBytes } from 'node:crypto';
import { mkdirSync, readFileSync, rmSync, statSync, writeFileSync } from 'node:fs';
import { join, resolve } from 'node:path';

const expectedHost = 'dpg-daoet2ad0e5s73808crg-a.singapore-postgres.render.com';
const sourceSecret = process.env.CHAINSCOPE_MIGRATION_RENDER_URL;
const keySecret = process.env.CHAINSCOPE_MIGRATION_KEY_B64;
const outputDirectory = resolve(process.env.CHAINSCOPE_BACKUP_OUT || '');
const image = 'postgres:18';

function fail(message) {
  throw new Error(message);
}

if (!sourceSecret || !keySecret || !process.env.CHAINSCOPE_BACKUP_OUT) {
  fail('Required migration secrets or output directory are missing.');
}

let source;
try {
  source = new URL(sourceSecret);
} catch {
  fail('The source URL is invalid. Its value was not logged.');
}
delete process.env.CHAINSCOPE_MIGRATION_RENDER_URL;
delete process.env.CHAINSCOPE_MIGRATION_KEY_B64;

if (!['postgres:', 'postgresql:'].includes(source.protocol) ||
    source.hostname !== expectedHost ||
    decodeURIComponent(source.username) !== 'chainscope' ||
    decodeURIComponent(source.pathname) !== '/chainscope') {
  fail('The source URL does not identify the expected Render database.');
}

let password;
try {
  password = decodeURIComponent(source.password);
} catch {
  fail('The source password encoding is invalid.');
}
if (!password) fail('The source URL is missing its database password.');

if (!/^[A-Za-z0-9+/]{43}=$/.test(keySecret)) {
  fail('The backup key is not a base64-encoded 32-byte value.');
}
const key = Buffer.from(keySecret, 'base64');
if (key.length !== 32) fail('The backup key has the wrong length.');

const port = source.port || '5432';
const dockerEnv = {
  ...process.env,
  PGPASSWORD: password,
  PGSSLMODE: 'require',
  PGCONNECT_TIMEOUT: '12',
};
const dockerBase = [
  'run', '--rm', '--network', 'host',
  '--user', `${process.getuid()}:${process.getgid()}`,
  '-e', 'PGPASSWORD', '-e', 'PGSSLMODE', '-e', 'PGCONNECT_TIMEOUT',
  '-v', `${outputDirectory}:/backup`, image,
];

function postgresCommand(command, args, timeoutMs = 30000) {
  return spawnSync('docker', [...dockerBase, command, ...args], {
    env: dockerEnv,
    encoding: 'utf8',
    timeout: timeoutMs,
    maxBuffer: 8 * 1024 * 1024,
  });
}

const delay = ms => new Promise(resolveDelay => setTimeout(resolveDelay, ms));

async function main() {
  const response = await fetch('https://api.ipify.org?format=json', {
    signal: AbortSignal.timeout(12000),
  });
  if (!response.ok) fail('Could not determine the runner public IP.');
  const { ip } = await response.json();
  if (typeof ip !== 'string' || !/^\d{1,3}(\.\d{1,3}){3}$/.test(ip)) {
    fail('The runner public IP is not a valid IPv4 address.');
  }
  if (ip !== process.env.CHAINSCOPE_RUNNER_IP) {
    fail('The runner public IP changed after the allowlist artifact was published. No dump was created.');
  }
  console.log(`Temporarily allow this single runner IP in Render: ${ip}/32`);
  console.log('Waiting up to 25 minutes for Render PostgreSQL readiness and verified application maintenance.');

  mkdirSync(outputDirectory, { recursive: true, mode: 0o700 });
  const pull = spawnSync('docker', ['pull', image], {
    stdio: 'ignore', timeout: 180000,
  });
  if (pull.status !== 0) fail('Could not obtain the PostgreSQL 18 client image.');

  const readyArgs = [
    '--host', expectedHost, '--port', port,
    '--username', 'chainscope', '--dbname', 'chainscope', '--timeout', '5',
  ];
  let ready = false;
  const deadline = Date.now() + 25 * 60 * 1000;
  let nextReminder = Date.now() + 60 * 1000;
  while (Date.now() < deadline) {
    const check = postgresCommand('pg_isready', readyArgs, 15000);
    if (check.status === 0) {
      ready = true;
      break;
    }
    if (Date.now() >= nextReminder) {
      console.log('Still waiting for Render PostgreSQL; confirm the /32 rule was saved.');
      nextReminder = Date.now() + 60 * 1000;
    }
    await delay(10000);
  }
  if (!ready) fail('Render PostgreSQL did not become ready. No dump was created.');

  console.log('Render PostgreSQL is ready; waiting for application maintenance before the dump.');
  let maintenanceSince = null;
  let nextMaintenanceReminder = Date.now() + 60 * 1000;
  while (Date.now() < deadline) {
    let maintenanceActive = false;
    try {
      const check = await fetch(
        `https://chainscope-web3.onrender.com/api/auth/csrf?migration_probe=${Date.now()}`,
        { redirect: 'manual', cache: 'no-store', signal: AbortSignal.timeout(20000) },
      );
      maintenanceActive = check.status === 503 &&
        check.headers.get('x-chainscope-maintenance') === '1';
      await check.body?.cancel();
    } catch {
      // A transient HTTP failure is not evidence that writes are frozen.
    }
    if (maintenanceActive) {
      maintenanceSince ??= Date.now();
      if (Date.now() - maintenanceSince >= 60 * 1000) break;
    } else {
      maintenanceSince = null;
    }
    if (Date.now() >= nextMaintenanceReminder) {
      console.log('Still waiting for 60 continuous seconds of verified application maintenance.');
      nextMaintenanceReminder = Date.now() + 60 * 1000;
    }
    await delay(10000);
  }
  if (maintenanceSince === null || Date.now() - maintenanceSince < 60 * 1000) {
    fail('Application maintenance was not verified for 60 seconds. No dump was created.');
  }

  const archivePath = join(outputDirectory, 'chainscope-render-latest.dump');
  const encryptedPath = join(outputDirectory, 'chainscope-render-latest.dump.enc');
  const manifestPath = join(outputDirectory, 'chainscope-render-latest.manifest.json');
  console.log('Render PostgreSQL is ready; creating the full custom-format dump.');
  const dump = postgresCommand('pg_dump', [
    '--host', expectedHost, '--port', port,
    '--username', 'chainscope', '--dbname', 'chainscope',
    '--no-password', '--format', 'custom', '--file', '/backup/chainscope-render-latest.dump',
  ], 10 * 60 * 1000);
  if (dump.status !== 0) {
    rmSync(archivePath, { force: true });
    fail('pg_dump failed. Diagnostic output was suppressed to protect credentials.');
  }

  const listing = postgresCommand('pg_restore', [
    '--list', '/backup/chainscope-render-latest.dump',
  ]);
  const tableDataEntries = (listing.stdout || '').split('\n')
    .filter(line => /;\s+\d+\s+\d+\s+TABLE DATA\s+public\s+/.test(line)).length;
  if (listing.status !== 0 || tableDataEntries < 1) {
    fail('The dump catalog is unreadable or contains no public table data.');
  }
  const fullRead = postgresCommand('pg_restore', [
    '--file', '/dev/null', '/backup/chainscope-render-latest.dump',
  ], 10 * 60 * 1000);
  if (fullRead.status !== 0) fail('A complete read of the dump failed.');

  const archiveSize = statSync(archivePath).size;
  if (archiveSize < 1000 || archiveSize > 100 * 1024 * 1024) {
    fail('The archive size is outside the safe artifact range. No upload will occur.');
  }
  const plaintext = readFileSync(archivePath);
  const plaintextSha256 = createHash('sha256').update(plaintext).digest('hex');
  const nonce = randomBytes(12);
  const cipher = createCipheriv('aes-256-gcm', key, nonce);
  const ciphertext = Buffer.concat([cipher.update(plaintext), cipher.final()]);
  const encrypted = Buffer.concat([
    Buffer.from('CSBK1'), nonce, ciphertext, cipher.getAuthTag(),
  ]);
  writeFileSync(encryptedPath, encrypted, { mode: 0o600, flag: 'wx' });
  writeFileSync(manifestPath, JSON.stringify({
    format: 'chainscope-encrypted-pg-dump-v1',
    createdAtUtc: new Date().toISOString(),
    sourceDatabase: 'chainscope',
    postgresMajor: 18,
    tableDataEntries,
    archiveBytes: archiveSize,
    archiveSha256: plaintextSha256,
    encryptedSha256: createHash('sha256').update(encrypted).digest('hex'),
  }, null, 2) + '\n', { mode: 0o600, flag: 'wx' });
  rmSync(archivePath);
  plaintext.fill(0);
  key.fill(0);
  console.log(`Encrypted and verified archive ready; ${tableDataEntries} table-data entries.`);
  console.log('The source database was not changed. Do not switch DATABASE_URL yet.');
}

main().catch(error => {
  console.error(`Migration backup stopped safely: ${error.message}`);
  process.exitCode = 1;
});
