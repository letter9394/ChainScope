import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { createCipheriv, createHash, randomBytes } from 'node:crypto';
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve, sep } from 'node:path';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';

test('the encrypted backup decrypts and verifies without printing the key', () => {
  const directory = mkdtempSync(join(tmpdir(), 'chainscope-crypto-test-'));
  try {
    const key = randomBytes(32);
    const plaintext = Buffer.from('Synthetic test archive, not database data.');
    const nonce = randomBytes(12);
    const cipher = createCipheriv('aes-256-gcm', key, nonce);
    const encrypted = Buffer.concat([
      Buffer.from('CSBK1'), nonce,
      cipher.update(plaintext), cipher.final(), cipher.getAuthTag(),
    ]);
    const encryptedPath = join(directory, 'archive.enc');
    const manifestPath = join(directory, 'manifest.json');
    const outputPath = join(directory, 'restored.dump');
    writeFileSync(encryptedPath, encrypted);
    writeFileSync(manifestPath, JSON.stringify({
      format: 'chainscope-encrypted-pg-dump-v1',
      sourceDatabase: 'chainscope',
      postgresMajor: 18,
      archiveBytes: plaintext.length,
      archiveSha256: createHash('sha256').update(plaintext).digest('hex'),
      encryptedSha256: createHash('sha256').update(encrypted).digest('hex'),
    }));
    const result = spawnSync(process.execPath, [
      join(dirname(fileURLToPath(import.meta.url)), 'decrypt-ci-backup.mjs'),
      encryptedPath, manifestPath, outputPath,
    ], {
      env: { ...process.env, CHAINSCOPE_MIGRATION_KEY_B64: key.toString('base64') },
      encoding: 'utf8',
    });
    assert.equal(result.status, 0, result.stderr);
    assert.deepEqual(readFileSync(outputPath), plaintext);
    assert.equal(result.stdout.includes(key.toString('base64')), false);
  } finally {
    const target = resolve(directory);
    const temporaryRoot = resolve(tmpdir());
    assert.ok(target.startsWith(temporaryRoot + sep));
    rmSync(target, { recursive: true, force: true });
  }
});
