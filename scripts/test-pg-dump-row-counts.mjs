import { strict as assert } from 'node:assert';
import { spawnSync } from 'node:child_process';
import { test } from 'node:test';
import { countCopyRows } from './pg-dump-row-counts.mjs';

test('counts COPY rows without interpreting field values', () => {
  const sql = [
    'SET statement_timeout = 0;',
    'COPY public.users (id, email) FROM stdin;',
    '1\ta@example.invalid',
    '2\tb@example.invalid',
    '\\.',
    'COPY public.events (id) FROM stdin;',
    '\\.',
    '',
  ].join('\n');
  assert.deepEqual([...countCopyRows(sql)], [['users', 2], ['events', 0]]);
});

test('rejects duplicate and truncated COPY blocks', () => {
  assert.throws(() => countCopyRows('COPY public.users (id) FROM stdin;\n1\n'), /Unterminated/);
  assert.throws(() => countCopyRows('COPY public.users (id) FROM stdin;\n\\.\nCOPY public.users (id) FROM stdin;\n\\.\n'), /Duplicate/);
});

if (process.env.CHAINSCOPE_TEST_ARCHIVE && process.env.CHAINSCOPE_PG_RESTORE) {
  test('counts all table data blocks in the locally verified backup', () => {
    const result = spawnSync(process.env.CHAINSCOPE_PG_RESTORE, [
      '--data-only', '--file=-', process.env.CHAINSCOPE_TEST_ARCHIVE,
    ], { encoding: 'utf8', maxBuffer: 128 * 1024 * 1024 });
    assert.equal(result.status, 0, 'pg_restore must read the full data stream');
    const counts = countCopyRows(result.stdout);
    assert.equal(counts.size, 11);
    assert.equal(counts.get('alembic_version'), 1);
  });
}
