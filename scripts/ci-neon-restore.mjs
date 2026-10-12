import { spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { existsSync, readFileSync, statSync, writeFileSync } from 'node:fs';
import { basename, dirname, resolve } from 'node:path';
import { countCopyRows } from './pg-dump-row-counts.mjs';

const [archiveArgument, manifestArgument] = process.argv.slice(2);
const targetSecret = process.env.CHAINSCOPE_MIGRATION_NEON_DIRECT_URL;
const reportPath = process.env.CHAINSCOPE_RESTORE_REPORT;
const priorReportJson = process.env.CHAINSCOPE_PRIOR_RESTORE_REPORT_JSON;
const replacePriorRestore = process.env.CHAINSCOPE_REPLACE_PRIOR_RESTORE === 'true';
const expectedHost = 'ep-lucky-frog-b392fzlp.c-4.ap-southeast-1.aws.neon.tech';

function fail(message) { throw new Error(message); }
if (!archiveArgument || !manifestArgument || !targetSecret || !reportPath) {
  fail('Verified archive, manifest, Neon secret, or report path is missing.');
}

let target;
try { target = new URL(targetSecret); }
catch { fail('The Neon target URL is invalid. Its value was not logged.'); }
delete process.env.CHAINSCOPE_MIGRATION_NEON_DIRECT_URL;
delete process.env.CHAINSCOPE_PRIOR_RESTORE_REPORT_JSON;
if (!['postgres:', 'postgresql:'].includes(target.protocol) ||
    target.hostname !== expectedHost ||
    decodeURIComponent(target.username) !== 'neondb_owner' ||
    decodeURIComponent(target.pathname) !== '/neondb' ||
    !target.password ||
    target.searchParams.get('sslmode') !== 'require' ||
    target.searchParams.get('channel_binding') !== 'require') {
  fail('The target must be the expected direct Neon database with TLS and channel binding.');
}

const archivePath = resolve(archiveArgument);
const manifestPath = resolve(manifestArgument);
const archiveDirectory = dirname(archivePath);
const archiveName = basename(archivePath);
const manifest = JSON.parse(readFileSync(manifestPath, 'utf8'));
if (manifest.format !== 'chainscope-encrypted-pg-dump-v1' ||
    manifest.sourceDatabase !== 'chainscope' ||
    manifest.postgresMajor !== 18 ||
    !Number.isInteger(manifest.tableDataEntries) || manifest.tableDataEntries < 1) {
  fail('Unexpected backup manifest.');
}
const archive = readFileSync(archivePath);
if (archive.length !== manifest.archiveBytes ||
    createHash('sha256').update(archive).digest('hex') !== manifest.archiveSha256) {
  fail('The decrypted archive does not match its manifest.');
}
if (statSync(archivePath).size > 100 * 1024 * 1024) {
  fail('The archive is outside the approved size range.');
}

const dockerEnv = {
  ...process.env,
  PGPASSWORD: decodeURIComponent(target.password),
  PGSSLMODE: 'verify-full',
  PGSSLROOTCERT: 'system',
  PGCHANNELBINDING: 'require',
  PGCONNECT_TIMEOUT: '20',
};
const dockerBase = [
  'run', '--rm', '--network', 'host',
  '--user', `${process.getuid()}:${process.getgid()}`,
  '-e', 'PGPASSWORD', '-e', 'PGSSLMODE', '-e', 'PGSSLROOTCERT',
  '-e', 'PGCHANNELBINDING', '-e', 'PGCONNECT_TIMEOUT',
  '-v', '/etc/ssl/certs/ca-certificates.crt:/etc/ssl/certs/ca-certificates.crt:ro',
  '-v', `${archiveDirectory}:/backup:ro`, 'postgres:18',
];
const connectionArgs = [
  '--host', expectedHost, '--port', target.port || '5432',
  '--username', 'neondb_owner', '--dbname', 'neondb', '--no-password',
];

function postgresCommand(command, args, timeoutMs = 30000, maxBuffer = 8 * 1024 * 1024) {
  return spawnSync('docker', [...dockerBase, command, ...args], {
    env: dockerEnv, encoding: 'utf8', timeout: timeoutMs, maxBuffer,
  });
}
function postgresFailureCategory(result) {
  const diagnostic = String(result.stderr || '');
  if (/password authentication failed|no password supplied/i.test(diagnostic)) return 'authentication rejected';
  if (/could not translate host name|name or service not known|temporary failure in name resolution/i.test(diagnostic)) return 'DNS resolution failed';
  if (/timeout expired|timed out|no route to host/i.test(diagnostic)) return 'network timeout';
  if (/connection refused|server closed the connection unexpectedly/i.test(diagnostic)) return 'connection refused or closed';
  if (/invalid sslrootcert|root certificate file.*does not exist|no root certificate|could not load root certificate/i.test(diagnostic)) return 'client trust store unavailable';
  if (/certificate verify failed|self-signed certificate|unable to get local issuer|certificate.*does not match|hostname.*does not match/i.test(diagnostic)) return 'server certificate validation failed';
  if (/channel binding.*(not supported|failed|not available)|channel binding required/i.test(diagnostic)) return 'channel-binding negotiation failed';
  if (/server does not support SSL|could not establish SSL connection|SSL SYSCALL error/i.test(diagnostic)) return 'TLS negotiation failed';
  if (/certificate|sslrootcert|SSL error|channel binding/i.test(diagnostic)) return 'other TLS or channel-binding error';
  if (/database .* does not exist|role .* does not exist/i.test(diagnostic)) return 'database or role not found';
  if (result.error?.code === 'ETIMEDOUT') return 'command timed out';
  return `unclassified client failure (exit ${result.status ?? 'unknown'})`;
}
function query(sql) {
  const result = postgresCommand('psql', [
    '-X', '-A', '-t', '-w', '-v', 'ON_ERROR_STOP=1',
    ...connectionArgs, '-c', sql,
  ], 60000);
  if (result.status !== 0) fail(`A Neon preflight or verification query failed: ${postgresFailureCategory(result)}. Raw diagnostics were suppressed.`);
  return result.stdout.trim();
}

async function main() {
  if (!existsSync('/etc/ssl/certs/ca-certificates.crt')) {
    fail('The CI runner system CA bundle is unavailable; restore was not started.');
  }
  const pull = spawnSync('docker', ['pull', 'postgres:18'], {
    stdio: 'ignore', timeout: 180000,
  });
  if (pull.status !== 0) fail('Could not obtain the PostgreSQL 18 client image.');

  const listing = postgresCommand('pg_restore', [
    '--list', `/backup/${archiveName}`,
  ]);
  if (listing.status !== 0) fail('Could not read the backup catalog.');
  const lines = listing.stdout.split(/\r?\n/);
  const schemaEntry = /^\d+;\s+\d+\s+\d+\s+SCHEMA - public(?:\s|$)/;
  if (lines.filter(line => schemaEntry.test(line)).length !== 1) {
    fail('Expected exactly one public-schema entry in the archive.');
  }
  const tableNames = lines.flatMap(line => {
    const match = /^\d+;\s+\d+\s+\d+\s+TABLE public ([a-z_][a-z0-9_]*)\s/.exec(line);
    return match ? [match[1]] : [];
  });
  const sequenceNames = lines.flatMap(line => {
    const match = /^\d+;\s+\d+\s+\d+\s+SEQUENCE public ([a-z_][a-z0-9_]*)\s/.exec(line);
    return match ? [match[1]] : [];
  });
  if (tableNames.length !== manifest.tableDataEntries || new Set(tableNames).size !== tableNames.length) {
    fail('The backup catalog table count is inconsistent.');
  }
  const dataSql = postgresCommand('pg_restore', [
    '--data-only', '--file=-', `/backup/${archiveName}`,
  ], 5 * 60 * 1000, 128 * 1024 * 1024);
  if (dataSql.status !== 0) fail('Could not read all table data from the archive.');
  const expectedRows = countCopyRows(dataSql.stdout);
  if (expectedRows.size !== tableNames.length ||
      tableNames.some(name => !expectedRows.has(name))) {
    fail('The archive table data blocks do not match its catalog.');
  }

  const identity = query("SELECT current_database() || ':' || current_user || ':' || current_setting('server_version_num')");
  const match = /^neondb:neondb_owner:(\d+)$/.exec(identity);
  if (!match || Number(match[1]) < 180000) {
    fail('The target database, owner, or PostgreSQL major version is unexpected.');
  }
  const existingObjects = query("SELECT c.relkind || ':' || c.relname FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relkind IN ('r','p','v','m','S','f') ORDER BY 1").split('\n').filter(Boolean);
  let priorReport;
  if (replacePriorRestore) {
    if (!priorReportJson) fail('The prior verified restore report is missing. Replacement was not started.');
    try { priorReport = JSON.parse(priorReportJson); }
    catch { fail('The prior verified restore report is invalid. Replacement was not started.'); }
    const priorTableNames = Object.keys(priorReport.rowCounts || {}).sort();
    const expectedObjects = [
      ...tableNames.map(name => `r:${name}`),
      ...sequenceNames.map(name => `S:${name}`),
    ].sort();
    if (priorReport.format !== 'chainscope-neon-restore-verification-v1' ||
        priorReport.sourceTableCount !== tableNames.length ||
        priorTableNames.join('\n') !== [...tableNames].sort().join('\n') ||
        existingObjects.sort().join('\n') !== expectedObjects.join('\n')) {
      fail('The existing Neon schema does not match the previous verified restore. Replacement was not started.');
    }
    for (const name of tableNames) {
      if (query(`SELECT count(*) FROM public.${name}`) !== String(priorReport.rowCounts[name])) {
        fail(`The existing Neon table ${name} changed since its verified restore. Replacement was not started.`);
      }
    }
    if (query('SELECT version_num FROM public.alembic_version') !== priorReport.alembicRevision) {
      fail('The existing Neon migration revision changed. Replacement was not started.');
    }
  } else if (existingObjects.length !== 0) {
    fail('The target public schema is not empty. Restore was not started.');
  }

  // Neon creates public already; omit only that one archive entry.
  const tocPath = resolve(archiveDirectory, 'chainscope-neon-restore.toc');
  writeFileSync(tocPath, lines.filter(line => !schemaEntry.test(line)).join('\n'), {
    mode: 0o600, flag: 'wx',
  });
  console.log(`${replacePriorRestore ? 'Prior verified copy is unchanged' : 'Target is empty'} and PostgreSQL 18; restoring ${tableNames.length} tables.`);
  const restore = postgresCommand('pg_restore', [
    ...connectionArgs, '--use-list=/backup/chainscope-neon-restore.toc',
    '--no-owner', '--no-acl', '--no-tablespaces',
    ...(replacePriorRestore ? ['--clean', '--if-exists'] : []),
    '--exit-on-error', '--single-transaction', `/backup/${archiveName}`,
  ], 10 * 60 * 1000);
  if (restore.status !== 0) {
    fail('Neon restore failed; diagnostic output was suppressed. Do not switch the app.');
  }

  const restoredTables = query("SELECT count(*) FROM pg_catalog.pg_tables WHERE schemaname='public'");
  if (Number(restoredTables) !== tableNames.length) fail('Neon table-count verification failed.');
  const rowCounts = {};
  for (const name of tableNames) {
    const count = query(`SELECT count(*) FROM public.${name}`);
    if (!/^\d+$/.test(count) || Number(count) !== expectedRows.get(name)) {
      fail(`Neon row-count verification failed for ${name}.`);
    }
    rowCounts[name] = Number(count);
  }
  const revision = query('SELECT version_num FROM public.alembic_version');
  if (!revision || revision.includes('\n')) fail('Neon migration revision verification failed.');
  const totalRows = Object.values(rowCounts).reduce((sum, count) => sum + count, 0);
  writeFileSync(reportPath, JSON.stringify({
    format: 'chainscope-neon-restore-verification-v1',
    checkedAtUtc: new Date().toISOString(),
    backupArchiveSha256: manifest.archiveSha256,
    sourceTableCount: tableNames.length,
    restoredTableCount: Number(restoredTables),
    rowCounts,
    totalRows,
    alembicRevision: revision,
  }, null, 2) + '\n', { mode: 0o600, flag: 'wx' });
  console.log(`Neon restore verified: ${tableNames.length} tables, ${totalRows} rows, Alembic revision present.`);
  console.log('Render production still uses the old database. Do not switch DATABASE_URL yet.');
}

main().catch(error => {
  console.error(`Neon restore stopped safely: ${error.message}`);
  process.exitCode = 1;
});
