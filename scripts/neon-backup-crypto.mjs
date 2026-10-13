import { createCipheriv, createDecipheriv, createHash, randomBytes } from 'node:crypto';
import {
  closeSync, openSync, readFileSync, readSync, rmSync, statSync, writeFileSync, writeSync,
} from 'node:fs';

const magic = Buffer.from('CSBK1');
const headerBytes = magic.length + 12;
const tagBytes = 16;
const chunkBytes = 1024 * 1024;
// Fourteen daily artifacts remain below the 500 MiB GitHub Free storage allowance.
export const maxArchiveBytes = 30 * 1024 * 1024;
export const expectedNeonHost = 'ep-lucky-frog-b392fzlp.c-4.ap-southeast-1.aws.neon.tech';

function backupKey(base64) {
  if (typeof base64 !== 'string' || !/^[A-Za-z0-9+/]{43}=$/.test(base64)) {
    throw new Error('The backup key is not a base64-encoded 32-byte value.');
  }
  const key = Buffer.from(base64, 'base64');
  if (key.length !== 32) throw new Error('The backup key has the wrong length.');
  return key;
}

function writeAll(fd, value) {
  let offset = 0;
  while (offset < value.length) {
    const written = writeSync(fd, value, offset, value.length - offset);
    if (written <= 0) throw new Error('Could not write the complete backup file.');
    offset += written;
  }
}

export function parseNeonBackupUrl(secret) {
  let url;
  try { url = new URL(secret); }
  catch { throw new Error('The Neon backup URL is invalid; its value was not logged.'); }
  if (!['postgres:', 'postgresql:'].includes(url.protocol) ||
      url.hostname !== expectedNeonHost ||
      decodeURIComponent(url.username) !== 'neondb_owner' ||
      decodeURIComponent(url.pathname) !== '/neondb' ||
      !url.password ||
      url.searchParams.get('sslmode') !== 'require' ||
      url.searchParams.get('channel_binding') !== 'require') {
    throw new Error('The source must be the expected direct Neon database with TLS and channel binding.');
  }
  return {
    host: expectedNeonHost,
    port: url.port || '5432',
    username: 'neondb_owner',
    database: 'neondb',
    password: decodeURIComponent(url.password),
  };
}

function validateManifest(manifest) {
  if (manifest.format !== 'chainscope-neon-encrypted-pg-dump-v1' ||
      manifest.sourceProvider !== 'neon' ||
      manifest.sourceDatabase !== 'neondb' ||
      manifest.postgresMajor !== 18 ||
      !Number.isInteger(manifest.tableDataEntries) || manifest.tableDataEntries < 11 ||
      !Number.isInteger(manifest.archiveBytes) ||
      manifest.archiveBytes < 1000 || manifest.archiveBytes > maxArchiveBytes ||
      !/^[a-f0-9]{64}$/.test(manifest.archiveSha256) ||
      !/^[a-f0-9]{64}$/.test(manifest.encryptedSha256)) {
    throw new Error('Unexpected Neon backup manifest.');
  }
}

export function encryptNeonArchive(archivePath, encryptedPath, manifestPath, keyBase64, tableDataEntries) {
  const archiveBytes = statSync(archivePath).size;
  if (archiveBytes < 1000 || archiveBytes > maxArchiveBytes) {
    throw new Error('The archive is outside the free-tier backup size limit.');
  }
  if (!Number.isInteger(tableDataEntries) || tableDataEntries < 11) {
    throw new Error('The archive has too few public table-data entries.');
  }
  const key = backupKey(keyBase64);
  const nonce = randomBytes(12);
  const header = Buffer.concat([magic, nonce]);
  const cipher = createCipheriv('aes-256-gcm', key, nonce);
  const plainHash = createHash('sha256');
  const encryptedHash = createHash('sha256');
  let input;
  let output;
  let failed = false;
  let createdEncrypted = false;
  let createdManifest = false;
  try {
    input = openSync(archivePath, 'r');
    output = openSync(encryptedPath, 'wx', 0o600);
    createdEncrypted = true;
    writeAll(output, header);
    encryptedHash.update(header);
    const buffer = Buffer.allocUnsafe(chunkBytes);
    let count = 0;
    while (true) {
      const read = readSync(input, buffer, 0, buffer.length, null);
      if (read === 0) break;
      const chunk = buffer.subarray(0, read);
      plainHash.update(chunk);
      const ciphertext = cipher.update(chunk);
      writeAll(output, ciphertext);
      encryptedHash.update(ciphertext);
      count += read;
    }
    if (count !== archiveBytes) throw new Error('The archive changed while it was being encrypted.');
    const final = cipher.final();
    const tag = cipher.getAuthTag();
    writeAll(output, final);
    writeAll(output, tag);
    encryptedHash.update(final);
    encryptedHash.update(tag);
    const manifest = {
      format: 'chainscope-neon-encrypted-pg-dump-v1',
      createdAtUtc: new Date().toISOString(),
      sourceProvider: 'neon',
      sourceDatabase: 'neondb',
      postgresMajor: 18,
      tableDataEntries,
      archiveBytes,
      archiveSha256: plainHash.digest('hex'),
      encryptedSha256: encryptedHash.digest('hex'),
    };
    writeFileSync(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`, {
      mode: 0o600, flag: 'wx',
    });
    createdManifest = true;
    return manifest;
  } catch (error) {
    failed = true;
    throw error;
  } finally {
    if (input !== undefined) closeSync(input);
    if (output !== undefined) closeSync(output);
    key.fill(0);
    if (failed) {
      if (createdManifest) rmSync(manifestPath, { force: true });
      if (createdEncrypted) rmSync(encryptedPath, { force: true });
    }
  }
}

export function verifyNeonEncryptedArchive(encryptedPath, manifestPath, keyBase64, outputPath) {
  const manifestBytes = statSync(manifestPath).size;
  if (manifestBytes < 100 || manifestBytes > 4096) {
    throw new Error('Unexpected backup manifest size.');
  }
  const manifest = JSON.parse(readFileSync(manifestPath, 'utf8'));
  validateManifest(manifest);
  const totalBytes = statSync(encryptedPath).size;
  if (totalBytes !== headerBytes + manifest.archiveBytes + tagBytes) {
    throw new Error('The encrypted archive has the wrong size.');
  }
  const key = backupKey(keyBase64);
  let input;
  let output;
  let failed = false;
  let createdOutput = false;
  try {
    input = openSync(encryptedPath, 'r');
    if (outputPath) {
      output = openSync(outputPath, 'wx', 0o600);
      createdOutput = true;
    }
    const header = Buffer.alloc(headerBytes);
    if (readSync(input, header, 0, headerBytes, 0) !== headerBytes ||
        !header.subarray(0, magic.length).equals(magic)) {
      throw new Error('Unexpected encrypted backup header.');
    }
    const tag = Buffer.alloc(tagBytes);
    if (readSync(input, tag, 0, tagBytes, totalBytes - tagBytes) !== tagBytes) {
      throw new Error('The encrypted backup authentication tag is missing.');
    }
    const decipher = createDecipheriv('aes-256-gcm', key, header.subarray(magic.length));
    decipher.setAuthTag(tag);
    const encryptedHash = createHash('sha256').update(header);
    const plainHash = createHash('sha256');
    const buffer = Buffer.allocUnsafe(chunkBytes);
    let position = headerBytes;
    let count = 0;
    while (position < totalBytes - tagBytes) {
      const length = Math.min(buffer.length, totalBytes - tagBytes - position);
      const read = readSync(input, buffer, 0, length, position);
      if (read === 0) throw new Error('The encrypted archive ended early.');
      const chunk = buffer.subarray(0, read);
      encryptedHash.update(chunk);
      const plaintext = decipher.update(chunk);
      plainHash.update(plaintext);
      if (output !== undefined) writeAll(output, plaintext);
      position += read;
      count += plaintext.length;
    }
    encryptedHash.update(tag);
    if (encryptedHash.digest('hex') !== manifest.encryptedSha256) {
      throw new Error('Encrypted archive checksum mismatch.');
    }
    let final;
    try { final = decipher.final(); }
    catch { throw new Error('Backup decryption/authentication failed.'); }
    plainHash.update(final);
    if (output !== undefined) writeAll(output, final);
    count += final.length;
    if (count !== manifest.archiveBytes || plainHash.digest('hex') !== manifest.archiveSha256) {
      throw new Error('Plaintext archive checksum or size mismatch.');
    }
    return manifest;
  } catch (error) {
    failed = true;
    throw error;
  } finally {
    if (input !== undefined) closeSync(input);
    if (output !== undefined) closeSync(output);
    key.fill(0);
    if (failed && createdOutput) rmSync(outputPath, { force: true });
  }
}
