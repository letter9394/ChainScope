import { spawnSync } from 'node:child_process';
import { existsSync, mkdirSync, rmSync } from 'node:fs';
import { join, resolve } from 'node:path';
import {
  encryptNeonArchive, parseNeonBackupUrl, verifyNeonEncryptedArchive,
} from './neon-backup-crypto.mjs';
import { verifyNeonArchiveRestores } from './verify-neon-restore.mjs';

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
    verifyNeonArchiveRestores(archivePath);
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
