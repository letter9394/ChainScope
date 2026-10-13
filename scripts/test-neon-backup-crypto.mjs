import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { randomBytes } from 'node:crypto';
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve, sep } from 'node:path';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';
import {
  encryptNeonArchive, parseNeonBackupUrl, verifyNeonEncryptedArchive,
} from './neon-backup-crypto.mjs';

test('only the expected direct Neon production endpoint is accepted', () => {
  const valid = 'postgresql://neondb_owner:dummy@ep-lucky-frog-b392fzlp.c-4.ap-southeast-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require';
  assert.equal(parseNeonBackupUrl(valid).database, 'neondb');
  assert.throws(() => parseNeonBackupUrl(valid.replace('.c-4.', '-pooler.c-4.')));
  assert.throws(() => parseNeonBackupUrl(valid.replace('/neondb?', '/wrong?')));
  assert.throws(() => parseNeonBackupUrl(valid.replace('channel_binding=require', 'channel_binding=disable')));
});

test('Neon archive encryption authenticates, decrypts, and rejects tampering', () => {
  const directory = mkdtempSync(join(tmpdir(), 'chainscope-neon-backup-test-'));
  try {
    const archivePath = join(directory, 'archive.dump');
    const encryptedPath = join(directory, 'archive.dump.enc');
    const manifestPath = join(directory, 'archive.manifest.json');
    const outputPath = join(directory, 'recovered.dump');
    const payload = randomBytes(2 * 1024 * 1024 + 99);
    const key = randomBytes(32).toString('base64');
    writeFileSync(archivePath, payload);
    const manifest = encryptNeonArchive(archivePath, encryptedPath, manifestPath, key, 11);
    assert.equal(manifest.sourceDatabase, 'neondb');
    assert.equal(verifyNeonEncryptedArchive(encryptedPath, manifestPath, key).archiveBytes, payload.length);
    verifyNeonEncryptedArchive(encryptedPath, manifestPath, key, outputPath);
    assert.deepEqual(readFileSync(outputPath), payload);
    const commandOutput = join(directory, 'command-recovered.dump');
    const command = spawnSync(process.execPath, [
      fileURLToPath(new URL('./decrypt-neon-backup.mjs', import.meta.url)),
      encryptedPath, manifestPath, commandOutput,
    ], {
      env: { ...process.env, CHAINSCOPE_MIGRATION_KEY_B64: key },
      encoding: 'utf8',
    });
    assert.equal(command.status, 0, command.stderr);
    assert.deepEqual(readFileSync(commandOutput), payload);
    assert.equal(command.stdout.includes(key), false);
    assert.throws(() => verifyNeonEncryptedArchive(encryptedPath, manifestPath, key, outputPath));
    assert.deepEqual(readFileSync(outputPath), payload);

    const existingManifest = join(directory, 'existing.manifest.json');
    const unusedEncrypted = join(directory, 'unused.dump.enc');
    writeFileSync(existingManifest, 'Keep this file.');
    assert.throws(() => encryptNeonArchive(
      archivePath, unusedEncrypted, existingManifest, key, 11,
    ));
    assert.equal(readFileSync(existingManifest, 'utf8'), 'Keep this file.');
    assert.equal(existsSync(unusedEncrypted), false);

    const wrongOutput = join(directory, 'wrong-key.dump');
    assert.throws(() => verifyNeonEncryptedArchive(
      encryptedPath, manifestPath, randomBytes(32).toString('base64'), wrongOutput,
    ));
    assert.equal(existsSync(wrongOutput), false);

    const tampered = readFileSync(encryptedPath);
    tampered[100] ^= 1;
    writeFileSync(encryptedPath, tampered);
    const tamperedOutput = join(directory, 'tampered.dump');
    assert.throws(() => verifyNeonEncryptedArchive(encryptedPath, manifestPath, key, tamperedOutput));
    assert.equal(existsSync(tamperedOutput), false);
  } finally {
    const target = resolve(directory);
    assert.ok(target.startsWith(resolve(tmpdir()) + sep));
    rmSync(target, { recursive: true, force: true });
  }
});
