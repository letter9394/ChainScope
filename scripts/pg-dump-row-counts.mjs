// Count rows in pg_restore's text COPY stream without retaining or logging row values.
export function countCopyRows(sql) {
  const counts = new Map();
  let current = null;
  for (const rawLine of sql.split('\n')) {
    const line = rawLine.endsWith('\r') ? rawLine.slice(0, -1) : rawLine;
    if (current !== null) {
      if (line === '\\.') {
        current = null;
      } else {
        counts.set(current, counts.get(current) + 1);
      }
      continue;
    }
    const match = /^COPY public\.([a-z_][a-z0-9_]*) \([^\n]*\) FROM stdin;$/.exec(line);
    if (match) {
      if (counts.has(match[1])) throw new Error('Duplicate table data block in archive.');
      current = match[1];
      counts.set(current, 0);
    }
  }
  if (current !== null) throw new Error('Unterminated table data block in archive.');
  return counts;
}
