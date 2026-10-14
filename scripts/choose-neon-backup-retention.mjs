import { appendFileSync, statSync } from 'node:fs';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const mib = 1024 * 1024;
const tiers = [
  { maxBytes: mib / 2, days: 90 },
  { maxBytes: 3 * mib, days: 30 },
  { maxBytes: 12 * mib, days: 7 },
  // The archive itself is capped at 30 MiB; encryption adds a 33-byte header/tag.
  { maxBytes: 30 * mib + 33, days: 3 },
];

export function retentionDaysForBytes(bytes) {
  if (!Number.isSafeInteger(bytes) || bytes <= 0) {
    throw new Error('The encrypted backup size is invalid.');
  }
  const tier = tiers.find(({ maxBytes }) => bytes <= maxBytes);
  if (!tier) throw new Error('The encrypted backup exceeds its safe retention limit.');
  return tier.days;
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    const encryptedPath = process.argv[2];
    const outputPath = process.env.GITHUB_OUTPUT;
    if (!encryptedPath || !outputPath) {
      throw new Error('The encrypted backup path or GitHub output file is missing.');
    }
    const info = statSync(encryptedPath);
    if (!info.isFile()) throw new Error('The encrypted backup is not a regular file.');
    const days = retentionDaysForBytes(info.size);
    appendFileSync(outputPath, `days=${days}\n`);
    console.log(`Encrypted backup retention: ${days} days for ${info.size} bytes.`);
  } catch (error) {
    console.error(`Backup retention selection failed: ${error.message}`);
    process.exitCode = 1;
  }
}
