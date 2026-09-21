const { test } = require('node:test');
const assert = require('node:assert/strict');
const { classify } = require('../static/js/lesson_timing.js');
const rows = [
  { start: 100, end: 200, dayStart: 0, dayEnd: 1000 },
  { start: 250, end: 350, dayStart: 0, dayEnd: 1000 },
  { start: 400, end: 500, dayStart: 0, dayEnd: 1000 },
];
test('before class, boundaries, break and end of day', () => {
  for (const [now, states] of [
    [50, ['next', '', '']], [100, ['current', '', '']],
    [200, ['past', 'next', '']], [250, ['past', 'current', '']],
    [350, ['past', 'past', 'next']], [500, ['past', 'past', 'past']],
  ]) assert.deepEqual(classify(rows, now), states);
});
test('midnight clears yesterday and can activate a new day in week view', () => {
  assert.deepEqual(classify(rows, 1000), ['', '', '']);
  assert.deepEqual(classify([...rows, { start: 1100, end: 1200, dayStart: 1000, dayEnd: 2000 }], 1000),
    ['', '', '', 'next']);
});
test('invalid and unknown times are never highlighted', () => {
  assert.deepEqual(classify([{ ...rows[0], start: NaN }, { ...rows[0], end: 0 },
    { ...rows[0], start: 0, end: 0 }], 150), ['', '', '']);
});
test('parallel current lessons suppress the next marker', () => {
  assert.deepEqual(classify([rows[0], { ...rows[0] }, rows[1]], 150), ['current', 'current', '']);
});
test('unsorted rows choose chronological next, not row position', () => {
  assert.deepEqual(classify([rows[2], rows[0], rows[1]], 50), ['', 'next', '']);
});
