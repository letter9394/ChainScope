import test from 'node:test';
import assert from 'node:assert/strict';
import { retentionDaysForBytes } from './choose-neon-backup-retention.mjs';

const mib = 1024 * 1024;

test('small encrypted archives retain a 90-day recovery window', () => {
  assert.equal(retentionDaysForBytes(1), 90);
  assert.equal(retentionDaysForBytes(mib / 2), 90);
  assert.equal(retentionDaysForBytes(mib / 2 + 1), 30);
});

test('larger archives trade retention for bounded free-tier storage', () => {
  assert.equal(retentionDaysForBytes(3 * mib), 30);
  assert.equal(retentionDaysForBytes(3 * mib + 1), 7);
  assert.equal(retentionDaysForBytes(12 * mib), 7);
  assert.equal(retentionDaysForBytes(12 * mib + 1), 3);
  assert.equal(retentionDaysForBytes(30 * mib + 33), 3);
});

test('missing, invalid, or oversized archives are rejected', () => {
  for (const size of [0, -1, 1.5, NaN, Infinity, 30 * mib + 34]) {
    assert.throws(() => retentionDaysForBytes(size));
  }
});
