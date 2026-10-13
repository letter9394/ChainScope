import { spawnSync } from 'node:child_process';
import { randomBytes } from 'node:crypto';
import { existsSync, statSync } from 'node:fs';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const image = 'postgres:18';
const requiredTables = ['alembic_version', 'users', 'user_alert_rules', 'user_alert_events'];

function runDocker(args, options = {}) {
  return spawnSync('docker', args, {
    stdio: 'ignore', timeout: 30000, ...options,
  });
}

function query(container, sql) {
  const result = runDocker([
    'exec', '--user', 'postgres', container, 'psql', '-X', '-A', '-t',
    '-v', 'ON_ERROR_STOP=1', '--dbname', 'postgres', '-c', sql,
  ], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] });
  if (result.status !== 0) throw new Error('The isolated restore verification query failed.');
  const value = Number(result.stdout.trim());
  if (!Number.isSafeInteger(value) || value < 0) {
    throw new Error('The isolated restore returned an invalid verification result.');
  }
  return value;
}

export function verifyNeonArchiveRestores(archiveArgument) {
  if (!archiveArgument || !existsSync(archiveArgument) || !statSync(archiveArgument).isFile()) {
    throw new Error('The archive for the isolated restore check is missing.');
  }
  const archivePath = resolve(archiveArgument);
  const name = `chainscope-neon-restore-check-${randomBytes(6).toString('hex')}`;
  const password = randomBytes(24).toString('hex');
  let started = false;
  try {
    const start = runDocker([
      'run', '--detach', '--network', 'none', '--name', name,
      '-e', `POSTGRES_PASSWORD=${password}`, image,
    ]);
    if (start.status !== 0) throw new Error('Could not start the isolated PostgreSQL restore check.');
    started = true;
    let ready = false;
    for (let attempt = 0; attempt < 20; attempt += 1) {
      const check = runDocker([
        'exec', '--user', 'postgres', name, 'pg_isready', '--host', '127.0.0.1',
      ], { timeout: 10000 });
      if (check.status === 0) { ready = true; break; }
      Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 2000);
    }
    if (!ready) throw new Error('The isolated PostgreSQL restore check did not become ready.');
    const copy = runDocker(['cp', archivePath, `${name}:/tmp/chainscope-neon-backup.dump`]);
    if (copy.status !== 0) throw new Error('Could not copy the archive into the isolated restore check.');
    const owner = runDocker([
      'exec', '--user', 'root', name, 'chown', 'postgres:postgres',
      '/tmp/chainscope-neon-backup.dump',
    ]);
    if (owner.status !== 0) throw new Error('Could not prepare the isolated archive for restoration.');
    const restore = runDocker([
      'exec', '--user', 'postgres', name, 'pg_restore',
      '--no-owner', '--no-acl', '--clean', '--if-exists',
      '--single-transaction', '--exit-on-error',
      '--dbname', 'postgres', '/tmp/chainscope-neon-backup.dump',
    ], { timeout: 10 * 60 * 1000 });
    if (restore.status !== 0) throw new Error('The archive could not be restored into isolated PostgreSQL.');
    const tableCount = query(name,
      "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE'");
    if (tableCount < 11) throw new Error('The isolated restore is missing expected public tables.');
    const requiredCount = query(name,
      `SELECT count(*) FROM pg_catalog.pg_tables WHERE schemaname = 'public' AND tablename IN (${requiredTables.map(table => `'${table}'`).join(', ')})`);
    if (requiredCount !== requiredTables.length) {
      throw new Error('The isolated restore is missing a required application table.');
    }
    const migrationRows = query(name, 'SELECT count(*) FROM public.alembic_version');
    if (migrationRows !== 1) throw new Error('The isolated restore has no unique migration revision.');
    console.log(`Isolated restore verified with ${tableCount} public tables and one migration revision.`);
    return tableCount;
  } finally {
    if (started && runDocker(['rm', '--force', name]).status !== 0) {
      throw new Error('Could not remove the isolated restore container.');
    }
  }
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try { verifyNeonArchiveRestores(process.argv[2]); }
  catch (error) {
    console.error(`Isolated Neon restore check failed: ${error.message}`);
    process.exitCode = 1;
  }
}
