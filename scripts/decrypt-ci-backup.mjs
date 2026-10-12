import { createDecipheriv, createHash } from 'node:crypto';
import { existsSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { basename } from 'node:path';

const [encryptedPath, manifestPath, outputPath] = process.argv.slice(2);
const keySecret = process.env.CHAINSCOPE_MIGRATION_KEY_B64;

if (!encryptedPath || !manifestPath || !outputPath || !keySecret) {
  throw new Error('Provide encrypted archive, manifest, output path, and backup key in the process environment.');
}
if (existsSync(outputPath) || existsSync(`${outputPath}.sha256`)) {
  throw new Error('The destination archive or checksum already exists; refusing to overwrite it.');
}
if (!/^[A-Za-z0-9+/]{43}=$/.test(keySecret)) {
  throw new Error('The backup key has an invalid format.');
}
const key = Buffer.from(keySecret, 'base64');
delete process.env.CHAINSCOPE_MIGRATION_KEY_B64;
if (key.length !== 32) throw new Error('The backup key has an invalid length.');

const manifest = JSON.parse(readFileSync(manifestPath, 'utf8'));
if (manifest.format !== 'chainscope-encrypted-pg-dump-v1' ||
    manifest.sourceDatabase !== 'chainscope' ||
    manifest.postgresMajor !== 18) {
  throw new Error('Unexpected backup manifest.');
}
const encrypted = readFileSync(encryptedPath);
if (encrypted.length < 5 + 12 + 16 ||
    encrypted.subarray(0, 5).toString('ascii') !== 'CSBK1') {
  throw new Error('Unexpected encrypted backup format.');
}
const encryptedSha256 = createHash('sha256').update(encrypted).digest('hex');
if (encryptedSha256 !== manifest.encryptedSha256) {
  throw new Error('Encrypted archive checksum mismatch.');
}

const nonce = encrypted.subarray(5, 17);
const tag = encrypted.subarray(encrypted.length - 16);
const ciphertext = encrypted.subarray(17, encrypted.length - 16);
let plaintext;
try {
  const decipher = createDecipheriv('aes-256-gcm', key, nonce);
  decipher.setAuthTag(tag);
  plaintext = Buffer.concat([decipher.update(ciphertext), decipher.final()]);
} catch {
  throw new Error('Backup decryption/authentication failed.');
} finally {
  key.fill(0);
}

const archiveSha256 = createHash('sha256').update(plaintext).digest('hex');
if (plaintext.length !== manifest.archiveBytes ||
    archiveSha256 !== manifest.archiveSha256) {
  plaintext.fill(0);
  throw new Error('Plaintext backup checksum or size mismatch.');
}

let createdOutput = false;
try {
  writeFileSync(outputPath, plaintext, { mode: 0o600, flag: 'wx' });
  createdOutput = true;
  writeFileSync(`${outputPath}.sha256`, `${archiveSha256}  ${basename(outputPath)}\n`, {
    mode: 0o600, flag: 'wx',
  });
} catch {
  if (createdOutput) rmSync(outputPath, { force: true });
  throw new Error('Could not write the verified local archive and checksum.');
}
plaintext.fill(0);
console.log('Encrypted backup authenticated; plaintext archive and SHA-256 sidecar written.');
