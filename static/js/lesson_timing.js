(function () {
  'use strict';

  function classify(rows, now) {
    var eligible = rows.filter(function (row) {
      return Number.isFinite(row.start) && Number.isFinite(row.end) && row.end > row.start &&
        row.dayStart <= now && now < row.dayEnd;
    });
    var hasCurrent = eligible.some(function (row) { return row.start <= now && now < row.end; });
    var next = Math.min.apply(null, eligible.filter(function (row) { return row.start > now; })
      .map(function (row) { return row.start; }));
    return rows.map(function (row) {
      if (eligible.indexOf(row) === -1) return '';
      if (now >= row.end) return 'past';
      if (now >= row.start) return 'current';
      return !hasCurrent && row.start === next ? 'next' : '';
    });
  }

  // The pure classifier is also exercised by Node's built-in test runner.
  if (typeof module !== 'undefined' && module.exports) module.exports = { classify: classify };
  if (typeof document === 'undefined') return;

  var labels = { past: 'Завершена', current: 'Сейчас идёт', next: 'Следующая' };
  var mountedAt = performance.now();
  var groups = Array.from(document.querySelectorAll('[data-timetable]')).map(function (root) {
    return {
      serverNow: Number(root.dataset.serverNow),
      rows: Array.from(root.querySelectorAll('[data-lesson-timing]')).map(function (node) {
        return { node: node, start: Number(node.dataset.start), end: Number(node.dataset.end),
          dayStart: Number(node.dataset.dayStart), dayEnd: Number(node.dataset.dayEnd) };
      })
    };
  });
  if (!groups.length) return;

  function update() {
    if (document.hidden) return;
    groups.forEach(function (group) {
      if (!Number.isFinite(group.serverNow) || group.serverNow <= 0) return;
      // Use the server clock and monotonic elapsed time, not the device's timezone/clock.
      var states = classify(group.rows, group.serverNow + performance.now() - mountedAt);
      group.rows.forEach(function (row, index) {
        var state = states[index];
        ['past', 'current', 'next'].forEach(function (name) {
          row.node.classList.toggle('lesson-is-' + name, state === name);
        });
        if (state === 'current') row.node.setAttribute('aria-current', 'time');
        else row.node.removeAttribute('aria-current');
        var label = row.node.querySelector('[data-timing-label]');
        if (label) {
          var text = labels[state] || '';
          if (label.textContent !== text) label.textContent = text;
          label.hidden = !text;
        }
      });
    });
  }
  update();
  window.setInterval(update, 15000);
  document.addEventListener('visibilitychange', update);
  window.addEventListener('pageshow', update);
})();
