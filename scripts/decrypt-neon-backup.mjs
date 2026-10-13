import { existsSync, rmSync, writeFileSync } from 'node:fs';
import { basename } from 'node:path';
import { verifyNeonEncryptedArchive } from './neon-backup-crypto.mjs';

const [encryptedPath, manifestPath, outputPath] = process.argv.slice(2);
let key = process.env.CHAINSCOPE_MIGRATION_KEY_B64;
delete process.env.CHAINSCOPE_MIGRATION_KEY_B64;
if (!encryptedPath || !manifestPath || !outputPath || !key) {
  throw new Error('Provide the encrypted archive, manifest, output path, and local backup key.');
}
if (existsSync(outputPath) || existsSync(`${outputPath}.sha256`)) {
  throw new Error('The destination archive or checksum already exists; refusing to overwrite it.');
}
try {
  const manifest = verifyNeonEncryptedArchive(encryptedPath, manifestPath, key, outputPath);
  writeFileSync(`${outputPath}.sha256`, `${manifest.archiveSha256}  ${basename(outputPath)}\n`, {
    mode: 0o600, flag: 'wx',
  });
  console.log('Neon backup authenticated; plaintext archive and SHA-256 sidecar written.');
} catch (error) {
  rmSync(outputPath, { force: true });
  throw error;
} finally {
  key = null;
}
