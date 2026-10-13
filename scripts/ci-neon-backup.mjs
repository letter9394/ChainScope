import { spawnSync } from 'node:child_process';
import { randomBytes } from 'node:crypto';
import { existsSync, mkdirSync, rmSync } from 'node:fs';
import { join, resolve } from 'node:path';
import {
  encryptNeonArchive, parseNeonBackupUrl, verifyNeonEncryptedArchive,
} from './neon-backup-crypto.mjs';

const image = 'postgres:18';
const outputArgument = process.env.CHAINSCOPE_BACKUP_OUT;
let sourceSecret = process.env.CHAINSCOPE_MIGRATION_NEON_DIRECT_URL;
let keySecret = process.env.CHAINSCOPE_MIGRATION_KEY_B64;
delete process.env.CHAINSCOPE_MIGRATION_NEON_DIRECT_URL;
delete process.env.CHAINSCOPE_MIGRATION_KEY_B64;

function fail(message) { throw new Error(message); }
if (!outputArgument || !sourceSecret || !keySecret) {
  fail('Required Neon backup secrets or output directory are missing.');
}
const source = parseNeonBackupUrl(sourceSecret);
sourceSecret = null;
const outputDirectory = resolve(outputArgument);
const archivePath = join(outputDirectory, 'chainscope-neon-latest.dump');
const encryptedPath = `${archivePath}.enc`;
const manifestPath = join(outputDirectory, 'chainscope-neon-latest.manifest.json');
const dockerEnv = {
  ...process.env,
  PGPASSWORD: source.password,
  PGSSLMODE: 'verify-full',
  PGSSLROOTCERT: 'system',
  PGCHANNELBINDING: 'require',
  PGCONNECT_TIMEOUT: '20',
};
source.password = null;
const dockerBase = [
  'run', '--rm', '--network', 'host',
  '--user', `${process.getuid()}:${process.getgid()}`,
  '-e', 'PGPASSWORD', '-e', 'PGSSLMODE', '-e', 'PGSSLROOTCERT',
  '-e', 'PGCHANNELBINDING', '-e', 'PGCONNECT_TIMEOUT',
  '-v', '/etc/ssl/certs/ca-certificates.crt:/etc/ssl/certs/ca-certificates.crt:ro',
  '-v', `${outputDirectory}:/backup`, image,
];
const connectionArgs = [
  '--host', source.host, '--port', source.port,
  '--username', source.username, '--dbname', source.database, '--no-password',
];
const readinessArgs = [
  '--host', source.host, '--port', source.port,
  '--username', source.username, '--dbname', source.database, '--timeout', '15',
];

function dockerClient(command, args, timeoutMs = 60000) {
  return spawnSync('docker', [...dockerBase, command, ...args], {
    env: dockerEnv, encoding: 'utf8', timeout: timeoutMs, maxBuffer: 8 * 1024 * 1024,
  });
}

function localRestoreDrill() {
  const name = `chainscope-neon-restore-check-${randomBytes(6).toString('hex')}`;
  const password = randomBytes(24).toString('hex');
  let started = false;
  try {
    const start = spawnSync('docker', [
      'run', '--detach', '--name', name,
      '-e', `POSTGRES_PASSWORD=${password}`, image,
    ], { stdio: 'ignore', timeout: 30000 });
    if (start.status !== 0) fail('Could not start the isolated PostgreSQL restore check.');
    started = true;
    let ready = false;
    for (let attempt = 0; attempt < 20; attempt += 1) {
      const check = spawnSync('docker', [
        'exec', '--user', 'postgres', name, 'pg_isready', '--host', '127.0.0.1',
      ], { stdio: 'ignore', timeout: 10000 });
      if (check.status === 0) { ready = true; break; }
      Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 2000);
    }
    if (!ready) fail('The isolated PostgreSQL restore check did not become ready.');
    const copy = spawnSync('docker', [
      'cp', archivePath, `${name}:/tmp/chainscope-neon-backup.dump`,
    ], { stdio: 'ignore', timeout: 30000 });
    if (copy.status !== 0) fail('Could not copy the archive into the isolated restore check.');
    const owner = spawnSync('docker', [
      'exec', '--user', 'root', name, 'chown', 'postgres:postgres',
      '/tmp/chainscope-neon-backup.dump',
    ], { stdio: 'ignore', timeout: 30000 });
    if (owner.status !== 0) fail('Could not prepare the isolated archive for restoration.');
    const restore = spawnSync('docker', [
      'exec', '--user', 'postgres', name, 'pg_restore',
      '--no-owner', '--no-acl', '--clean', '--if-exists',
      '--single-transaction', '--exit-on-error',
      '--dbname', 'postgres', '/tmp/chainscope-neon-backup.dump',
    ], { stdio: 'ignore', timeout: 10 * 60 * 1000 });
    if (restore.status !== 0) fail('The archive could not be restored into isolated PostgreSQL.');
    const verify = spawnSync('docker', [
      'exec', '--user', 'postgres', name, 'psql', '-X', '-A', '-t',
      '-v', 'ON_ERROR_STOP=1', '--dbname', 'postgres',
      '-c', "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE'",
    ], { encoding: 'utf8', timeout: 30000 });
    if (verify.status !== 0 || Number(verify.stdout.trim()) < 11) {
      fail('The isolated restore is missing expected public tables.');
    }
  } finally {
    if (started) spawnSync('docker', ['rm', '--force', name], {
      stdio: 'ignore', timeout: 30000,
    });
  }
}

function main() {
  if (!existsSync('/etc/ssl/certs/ca-certificates.crt')) {
    fail('The CI runner system CA bundle is unavailable.');
  }
  mkdirSync(outputDirectory, { recursive: true, mode: 0o700 });
  const pull = spawnSync('docker', ['pull', image], {
    stdio: 'ignore', timeout: 180000,
  });
  if (pull.status !== 0) fail('Could not obtain the PostgreSQL 18 client image.');
  let ready = false;
  for (let attempt = 0; attempt < 3; attempt += 1) {
    if (dockerClient('pg_isready', readinessArgs, 30000).status === 0) {
      ready = true;
      break;
    }
    if (attempt < 2) Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 5000);
  }
  if (!ready) fail('The Neon production database is not ready after three attempts. No backup was created.');
  console.log('Creating a consistent PostgreSQL custom-format backup of Neon production.');
  try {
    const dump = dockerClient('pg_dump', [
      ...connectionArgs, '--format', 'custom',
      '--file', '/backup/chainscope-neon-latest.dump',
    ], 10 * 60 * 1000);
    if (dump.status !== 0) fail('pg_dump failed. Raw diagnostics were suppressed to protect credentials.');
    const listing = dockerClient('pg_restore', [
      '--list', '/backup/chainscope-neon-latest.dump',
    ]);
    if (listing.status !== 0) fail('The backup catalog could not be read.');
    const tables = new Set((listing.stdout || '').split(/\r?\n/)
      .map(line => /;\s+\d+\s+\d+\s+TABLE DATA\s+public\s+(\S+)/.exec(line)?.[1])
      .filter(Boolean));
    for (const required of ['alembic_version', 'users', 'user_alert_rules', 'user_alert_events']) {
      if (!tables.has(required)) fail('The backup is missing a required application table.');
    }
    if (tables.size < 11) fail('The backup contains fewer than 11 public table-data entries.');
    const fullRead = dockerClient('pg_restore', [
      '--file', '/dev/null', '/backup/chainscope-neon-latest.dump',
    ], 10 * 60 * 1000);
    if (fullRead.status !== 0) fail('A complete read of the backup failed.');
    localRestoreDrill();
    console.log(`Isolated restore verified with ${tables.size} public tables.`);
    encryptNeonArchive(archivePath, encryptedPath, manifestPath, keySecret, tables.size);
    verifyNeonEncryptedArchive(encryptedPath, manifestPath, keySecret);
    console.log('Encrypted archive authenticated and ready for private-key recovery.');
  } finally {
    rmSync(archivePath, { force: true });
    keySecret = null;
  }
}

try { main(); }
catch (error) {
  console.error(`Neon backup stopped safely: ${error.message}`);
  process.exitCode = 1;
}
