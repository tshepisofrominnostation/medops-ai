/* Analytics, in the browser.
 *
 * Mirrors app/analytics.py and app/lifecycle.py so the dashboard on the page reports the
 * same numbers the service and the PDF report do. Key names are deliberately identical:
 * scripts/check_app_parity.mjs compares this output with Python's on the same records and
 * fails on any difference, which is also what keeps the two from drifting later.
 */
(function (root) {
  'use strict';

  var CATEGORIES = ['IT & Medical Tech', 'HR', 'Finance', 'Operations'];
  var PRIORITIES = ['High', 'Medium', 'Low'];
  var STATUSES = ['Open', 'In Progress', 'Resolved'];
  var SLA_TARGET_MINUTES = { High: 15, Medium: 120, Low: 480 };
  var DATE_KEYS = ['timestamp', 'created_date', 'date'];

  function configure(taxonomy) {
    if (!taxonomy) return;
    CATEGORIES = taxonomy.categories.slice();
    PRIORITIES = taxonomy.priorities.slice();
    STATUSES = taxonomy.statuses.slice();
    SLA_TARGET_MINUTES = taxonomy.sla_targets_minutes;
  }

  function recordDate(rec) {
    for (var i = 0; i < DATE_KEYS.length; i++) {
      var stamp = rec[DATE_KEYS[i]];
      if (typeof stamp === 'string' && stamp.length >= 10) return stamp.slice(0, 10);
    }
    return null;
  }

  function parseTs(value) {
    if (!value || typeof value !== 'string') return null;
    var ms = Date.parse(value);
    return isNaN(ms) ? null : ms;
  }

  function minutesBetween(start, end) {
    var a = parseTs(start), b = parseTs(end);
    if (a === null || b === null) return null;
    var minutes = (b - a) / 60000;
    // Bad data (a response before creation) is refused, not averaged in as a negative.
    return minutes >= 0 ? round2(minutes) : null;
  }

  var round2 = function (x) { return Math.round(x * 100) / 100; };
  var round4 = function (x) { return Math.round(x * 10000) / 10000; };

  function mean(values) {
    if (!values.length) return null;
    return round2(values.reduce(function (a, b) { return a + b; }, 0) / values.length);
  }

  function median(values) {
    if (!values.length) return null;
    var v = values.slice().sort(function (a, b) { return a - b; });
    var mid = Math.floor(v.length / 2);
    return round2(v.length % 2 ? v[mid] : (v[mid - 1] + v[mid]) / 2);
  }

  function statusOf(rec) {
    if (STATUSES.indexOf(rec.status) !== -1) return rec.status;
    if (rec.resolved_at) return 'Resolved';
    if (rec.first_response_at) return 'In Progress';
    return 'Open';
  }

  function responseMinutes(rec) { return minutesBetween(rec.timestamp, rec.first_response_at); }
  function resolutionMinutes(rec) { return minutesBetween(rec.timestamp, rec.resolved_at); }

  function slaMet(rec) {
    var mins = responseMinutes(rec);
    var target = SLA_TARGET_MINUTES[rec.priority];
    if (mins === null || target === undefined) return null;
    return mins <= target;
  }

  function buildAnalytics(records, start, end) {
    var rows = records || [];
    if (start || end) {
      rows = rows.filter(function (rec) {
        var day = recordDate(rec);
        if (day === null) return false;
        if (start && day < start) return false;
        if (end && day > end) return false;
        return true;
      });
    }

    var byCategory = {}, byPriority = {}, byDepartment = {}, byDay = {}, byStatus = {};
    CATEGORIES.forEach(function (c) { byCategory[c] = 0; });
    PRIORITIES.forEach(function (p) { byPriority[p] = 0; });
    STATUSES.forEach(function (s) { byStatus[s] = 0; });

    var respAll = [], respByPrio = {}, respByCat = {}, resolution = [];
    PRIORITIES.forEach(function (p) { respByPrio[p] = []; });
    CATEGORIES.forEach(function (c) { respByCat[c] = []; });
    var slaByPrio = {};
    PRIORITIES.forEach(function (p) { slaByPrio[p] = { met: 0, measured: 0 }; });
    var categoryByDay = {};

    rows.forEach(function (rec) {
      if (byCategory[rec.category] !== undefined) byCategory[rec.category] += 1;
      if (byPriority[rec.priority] !== undefined) byPriority[rec.priority] += 1;
      if (rec.assigned_to) byDepartment[rec.assigned_to] = (byDepartment[rec.assigned_to] || 0) + 1;
      var day = recordDate(rec);
      if (day) byDay[day] = (byDay[day] || 0) + 1;

      byStatus[statusOf(rec)] += 1;

      var rm = responseMinutes(rec);
      if (rm !== null) {
        respAll.push(rm);
        if (respByPrio[rec.priority]) respByPrio[rec.priority].push(rm);
        if (respByCat[rec.category]) respByCat[rec.category].push(rm);
      }
      var rs = resolutionMinutes(rec);
      if (rs !== null) resolution.push(rs);
      var met = slaMet(rec);
      if (met !== null && slaByPrio[rec.priority]) {
        slaByPrio[rec.priority].measured += 1;
        slaByPrio[rec.priority].met += (met ? 1 : 0);
      }
      if (day && byCategory[rec.category] !== undefined) {
        if (!categoryByDay[day]) categoryByDay[day] = {};
        categoryByDay[day][rec.category] = (categoryByDay[day][rec.category] || 0) + 1;
      }
    });

    var total = rows.length;
    var high = byPriority.High || 0;
    var days = Object.keys(byDay).sort();
    var undated = rows.filter(function (rec) { return recordDate(rec) === null; }).length;
    var measured = PRIORITIES.reduce(function (n, p) { return n + slaByPrio[p].measured; }, 0);
    var metTotal = PRIORITIES.reduce(function (n, p) { return n + slaByPrio[p].met; }, 0);

    var deptPairs = Object.keys(byDepartment).map(function (k) { return [k, byDepartment[k]]; })
      .sort(function (a, b) { return b[1] - a[1] || (a[0] < b[0] ? -1 : 1); });
    var byDepartmentOut = {};
    deptPairs.forEach(function (pair) { byDepartmentOut[pair[0]] = pair[1]; });

    var slaByPrioOut = {};
    PRIORITIES.forEach(function (p) {
      var v = slaByPrio[p];
      slaByPrioOut[p] = v.measured ? round4(v.met / v.measured) : null;
    });

    return {
      total_tickets: total,
      date_range: { first: days.length ? days[0] : null, last: days.length ? days[days.length - 1] : null },
      window: { start: start || null, end: end || null },
      by_category: byCategory,
      by_priority: byPriority,
      by_department: byDepartmentOut,
      by_day: days.map(function (d) { return { date: d, count: byDay[d] }; }),
      rates: {
        high_priority_share: total ? round4(high / total) : 0,
        tickets_per_day: days.length ? round2(total / days.length) : 0
      },
      undated_tickets: undated,
      by_status: byStatus,
      by_category_by_day: Object.keys(categoryByDay).sort().map(function (d) {
        var row = { date: d };
        CATEGORIES.forEach(function (c) { row[c] = categoryByDay[d][c] || 0; });
        return row;
      }),
      response_time: {
        measured_tickets: respAll.length,
        unmeasured_tickets: total - respAll.length,
        mean_minutes: mean(respAll),
        median_minutes: median(respAll),
        worst_minutes: respAll.length ? Math.max.apply(null, respAll) : null,
        by_priority: (function () {
          var o = {};
          PRIORITIES.forEach(function (p) { o[p] = mean(respByPrio[p]); });
          return o;
        })(),
        by_category: (function () {
          var o = {};
          CATEGORIES.forEach(function (c) { o[c] = mean(respByCat[c]); });
          return o;
        })(),
        mean_resolution_minutes: mean(resolution)
      },
      sla: {
        targets_minutes: SLA_TARGET_MINUTES,
        measured_tickets: measured,
        attainment: measured ? round4(metTotal / measured) : null,
        by_priority: slaByPrioOut
      }
    };
  }

  /* The 7-day window ending on `end` (default: latest dated ticket), as in
   * app.insights.week_window. */
  function weekWindow(records, end, days) {
    days = days || 7;
    var last = end || null;
    if (!last) {
      var dated = records.map(recordDate).filter(Boolean).sort();
      last = dated.length ? dated[dated.length - 1] : new Date().toISOString().slice(0, 10);
    }
    var stop = new Date(last + 'T00:00:00Z');
    var start = new Date(stop.getTime() - (days - 1) * 86400000);
    return { start: start.toISOString().slice(0, 10), end: last };
  }

  function shiftWindow(win, days) {
    var stop = new Date(win.start + 'T00:00:00Z');
    var prevEnd = new Date(stop.getTime() - 86400000);
    var prevStart = new Date(prevEnd.getTime() - (days - 1) * 86400000);
    return { start: prevStart.toISOString().slice(0, 10), end: prevEnd.toISOString().slice(0, 10) };
  }

  root.MedOpsAnalytics = {
    configure: configure,
    CATEGORIES: function () { return CATEGORIES.slice(); },
    PRIORITIES: function () { return PRIORITIES.slice(); },
    STATUSES: function () { return STATUSES.slice(); },
    SLA_TARGET_MINUTES: function () { return SLA_TARGET_MINUTES; },
    buildAnalytics: buildAnalytics,
    weekWindow: weekWindow,
    shiftWindow: shiftWindow,
    recordDate: recordDate,
    minutesBetween: minutesBetween,
    statusOf: statusOf,
    responseMinutes: responseMinutes,
    resolutionMinutes: resolutionMinutes,
    slaMet: slaMet,
    mean: mean,
    median: median
  };
})(typeof window !== 'undefined' ? window : globalThis);
