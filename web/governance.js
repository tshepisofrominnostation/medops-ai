/* Governance and forecasting, in the browser.
 *
 * Four things used to exist only in Python, and the published console has no server to
 * ask, so the page needs its own copy:
 *
 *   forecastVolume  <- app/forecast.py
 *   compareMethods  <- app/forecast_compare.py
 *   prioritize / runBiasAudit <- app/prioritizer.py, app/bias_audit.py
 *   buildDecisionRecord / signalsFor / languageHint / transparencyNote <- app/decision_log.py
 *
 * A second implementation is only honest if it can be shown to agree, so:
 * scripts/make_governance_fixtures.py runs the REAL Python functions over the demo
 * series, synthetic series, every matched pair and a spread of messages, and
 * scripts/check_governance_parity.mjs runs this file in a vm and compares every value.
 * The two are meant to be identical, and the check fails loudly when they are not.
 * The one place they are NOT identical on purpose is the message fingerprint - see
 * fingerprint() below.
 */
(function (root) {
  'use strict';

  /* ------------------------------------------------------------------ numbers */

  /* Python's round() rounds the EXACT binary value of the float half-to-even, so
   * round(2.675, 2) is 2.67 (the stored double is 2.67499999999999982...) while
   * Math.round(2.675 * 100) / 100 is 2.68. Every number this file reports goes through
   * Python, so every number goes through roundHalfEven here.
   *
   * Method: split the double into mantissa * 2^exp with BigInt, scale by 10^n in
   * integer arithmetic, round the remainder with ties to even, then divide once. IEEE
   * division is correctly rounded, so Number(q)/10^n is the nearest double to exactly
   * the decimal CPython returns.
   */
  var HAS_BIGINT = typeof BigInt === 'function';
  var BIG_ONE = HAS_BIGINT ? BigInt(1) : null;
  var BIG_ZERO = HAS_BIGINT ? BigInt(0) : null;
  var BIG_TWO = HAS_BIGINT ? BigInt(2) : null;

  function decompose(x) {
    var view = new DataView(new ArrayBuffer(8));
    view.setFloat64(0, x, false);
    var hi = view.getUint32(0, false);
    var lo = view.getUint32(4, false);
    var negative = (hi >>> 31) === 1;
    var expBits = (hi >>> 20) & 0x7ff;
    var mant = (BigInt(hi & 0xfffff) << BigInt(32)) | BigInt(lo);
    var exp;
    if (expBits === 0) {
      exp = -1074;
    } else {
      mant = mant | (BIG_ONE << BigInt(52));
      exp = expBits - 1075;
    }
    return { m: negative ? -mant : mant, e: exp };
  }

  function pow10Big(n) {
    var out = BIG_ONE;
    for (var i = 0; i < n; i++) out = out * BigInt(10);
    return out;
  }

  function roundHalfEvenFallback(x, digits) {
    // Only reached on an engine without BigInt/DataView. Cannot be exact on ties.
    var f = Math.pow(10, digits);
    var scaled = x * f;
    var floor = Math.floor(scaled);
    var diff = scaled - floor;
    var q;
    if (diff > 0.5) q = floor + 1;
    else if (diff < 0.5) q = floor;
    else q = (floor % 2 === 0) ? floor : floor + 1;
    return q / f;
  }

  function roundHalfEven(value, ndigits) {
    var digits = ndigits || 0;
    var x = Number(value);
    if (!isFinite(x)) return x;
    if (!HAS_BIGINT) return roundHalfEvenFallback(x, digits);
    var parts = decompose(x);
    var scale = pow10Big(digits);
    var num = parts.m * scale;
    var den = BIG_ONE;
    if (parts.e >= 0) {
      num = num << BigInt(parts.e);
    } else {
      den = BIG_ONE << BigInt(-parts.e);
    }
    var q = num / den;                     // BigInt division truncates toward zero
    var r = num % den;
    if (r !== BIG_ZERO) {
      var twice = (r < BIG_ZERO ? -r : r) * BIG_TWO;
      if (twice > den || (twice === den && (q % BIG_TWO) !== BIG_ZERO)) {
        q += (num < BIG_ZERO ? -BIG_ONE : BIG_ONE);
      }
    }
    return Number(q) / Number(scale);
  }

  function round2(x) { return roundHalfEven(x, 2); }
  function round1(x) { return roundHalfEven(x, 1); }
  function round3(x) { return roundHalfEven(x, 3); }

  /* Python's f"{v:.2f}". Both sides use an explicit 2-decimal format inside the verdict
   * sentences on purpose: Python's statistics.mean returns an int when the mean happens
   * to be whole, so an implicit format would print "0" there and "0.0" here. */
  function pyFixed(v, digits) {
    return roundHalfEven(v, digits).toFixed(digits);
  }

  /* Python's f"{v:+.2f}". */
  function pySignedFixed(v, digits) {
    var d = digits === undefined ? 2 : digits;
    var rounded = roundHalfEven(v, d);
    var negative = rounded < 0 || Object.is(rounded, -0);
    return (negative ? '-' : '+') + Math.abs(rounded).toFixed(d);
  }

  function sumOf(values) {
    var total = 0;
    for (var i = 0; i < values.length; i++) total += values[i];
    return total;
  }

  function meanOf(values) {
    return sumOf(values) / values.length;
  }

  /* ------------------------------------------------------------------- dates */

  /* Days are added in UTC on purpose: a local-time add would shift the ISO date
   * across a DST boundary and put the forecast on the wrong day. */
  function addDays(iso, days) {
    var ms = Date.parse(iso + 'T00:00:00Z');
    if (isNaN(ms)) return null;
    return new Date(ms + days * 86400000).toISOString().slice(0, 10);
  }

  function utcToday() {
    return new Date().toISOString().slice(0, 10);
  }

  function weekdayOf(iso) {
    // Python's date.weekday(): Monday = 0.
    var ms = Date.parse(iso + 'T00:00:00Z');
    if (isNaN(ms)) return null;
    return (new Date(ms).getUTCDay() + 6) % 7;
  }

  /* ---------------------------------------------------------------- forecast */

  var FORECAST_METHOD = 'moving_average_7 + linear_trend (50/50 blend)';

  /* Daily counts, oldest first, optionally limited to the most recent N days.
   * app.forecast._series would raise TypeError on a row with no date; here such a row
   * simply sorts last. Fixtures never contain one, so this only widens the input the
   * page tolerates - it does not change a result. */
  function forecastSeries(byDay, historyDays) {
    var rows = (byDay || []).slice().sort(function (a, b) {
      if (a.date < b.date) return -1;
      if (a.date > b.date) return 1;
      return 0;
    });
    var counts = rows.map(function (r) { return Math.trunc(Number(r.count)); });
    if (historyDays && historyDays > 0) counts = counts.slice(-historyDays);
    return counts;
  }

  /* Least-squares fit of y against x = 0..n-1. Returns {a: intercept, b: slope}. */
  function linfit(y) {
    var n = y.length;
    if (n === 0) return { a: 0, b: 0 };
    if (n === 1) return { a: y[0], b: 0 };
    var meanX = (n - 1) / 2;
    var meanY = sumOf(y) / n;
    var num = 0;
    var den = 0;
    for (var i = 0; i < n; i++) {
      num += (i - meanX) * (y[i] - meanY);
      den += (i - meanX) * (i - meanX);
    }
    var slope = den ? num / den : 0;
    return { a: meanY - slope * meanX, b: slope };
  }

  function movingAverage(values, window) {
    if (!values.length) return 0;
    var tail = values.slice(-window);
    return sumOf(tail) / tail.length;
  }

  function forecastVolume(byDay, horizon, historyDays) {
    var h = (horizon === undefined || horizon === null) ? 7 : Math.trunc(horizon);
    var history = forecastSeries(byDay, historyDays);
    if (!history.length) {
      return {
        method: 'none', horizon: h, history_days: 0, reliable: false,
        backtest_mae: null, predicted_total: 0, forecast: []
      };
    }

    // Backtest on the tail: fit on the first 70%, score on the last 30%. No peeking.
    var split = Math.max(2, Math.trunc(history.length * 0.7));
    var backtestMae = null;
    if (history.length - split >= 2) {
      var fit = linfit(history.slice(0, split));
      var errs = [];
      for (var i = 0; i < history.length - split; i++) {
        errs.push(Math.abs((fit.a + fit.b * (split + i)) - history[split + i]));
      }
      backtestMae = round2(sumOf(errs) / errs.length);
    }

    var full = linfit(history);
    var ma = movingAverage(history, Math.min(7, history.length));
    var reliable = history.length >= 5;

    var lastDay = null;
    var rows = byDay || [];
    for (var r = 0; r < rows.length; r++) {
      if (lastDay === null || rows[r].date > lastDay) lastDay = rows[r].date;
    }
    // app.forecast falls back to date.today() (LOCAL) when the last date will not
    // parse; the browser uses the UTC day. Only reachable with unparseable input.
    var start = lastDay ? addDays(lastDay, 0) : utcToday();
    if (!start) start = utcToday();

    var forecast = [];
    for (var step = 0; step < h; step++) {
      var trend = full.a + full.b * (history.length - 1 + step);
      var blended = 0.5 * trend + 0.5 * ma;
      var value = Math.max(0, roundHalfEven(blended));
      forecast.push({ date: addDays(start, step + 1), predicted: value });
    }

    return {
      method: FORECAST_METHOD,
      horizon: h,
      history_days: history.length,
      reliable: reliable,
      slope_per_day: round3(full.b),
      recent_daily_average: round2(ma),
      backtest_mae: backtestMae,
      predicted_total: sumOf(forecast.map(function (f) { return f.predicted; })),
      forecast: forecast
    };
  }

  /* -------------------------------------------------- forecast method comparison */

  var MIN_DAYS = 14;           // below this a comparison is not worth publishing
  var MIN_EVAL_POINTS = 5;     // below this the ranking is not stable
  var BOOTSTRAP_ROUNDS = 2000;

  /* The bootstrap is the only part of this module Python and JavaScript cannot share
   * through a library, because Python's random.Random is a Mersenne Twister and the
   * browser has no equivalent. app/forecast_compare.py therefore runs this same
   * mulberry32 (ported there), so both sides draw the same 2000 resamples and report
   * the same interval. The numbers are still a bootstrap; they are just reproducible. */
  function mulberry32(seed) {
    var a = seed | 0;
    return function () {
      a = (a + 0x6D2B79F5) | 0;
      var t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  function flatAverage(y, dates, t) {
    var window = y.slice(Math.max(0, t - 7), t);
    return window.length ? meanOf(window) : 0;
  }

  function weekdayMean(y, dates, t) {
    var target = dates[t];
    var same = [];
    for (var i = 0; i < t; i++) {
      if (dates[i] === target) same.push(y[i]);
    }
    return same.length ? meanOf(same) : flatAverage(y, dates, t);
  }

  function yesterdayValue(y, dates, t) {
    return t >= 1 ? y[t - 1] : 0;
  }

  /* Insertion order is Python's dict order and is the tie-break for equal MAEs. */
  var COMPARE_METHODS = [
    ['flat 7-day average', flatAverage],
    ['same weekday, all past weeks', weekdayMean],
    ['yesterday repeated', yesterdayValue]
  ];

  function compareSeries(byDay) {
    var rows = (byDay || []).filter(function (r) { return r && r.date; })
      .slice()
      .sort(function (a, b) {
        if (a.date < b.date) return -1;
        if (a.date > b.date) return 1;
        return 0;
      });
    var dates = rows.map(function (r) { return weekdayOf(r.date); });
    var y = rows.map(function (r) { return Math.trunc(Number(r.count === undefined ? 0 : r.count)); });
    return { y: y, dates: dates };
  }

  function percentileBootstrap(diffs, seed) {
    var rand = mulberry32(seed);
    var n = diffs.length;
    var boots = [];
    for (var round = 0; round < BOOTSTRAP_ROUNDS; round++) {
      var total = 0;
      for (var i = 0; i < n; i++) total += diffs[Math.floor(rand() * n)];
      boots.push(total / n);
    }
    boots.sort(function (a, b) { return a - b; });
    return [
      boots[Math.trunc(0.025 * BOOTSTRAP_ROUNDS)],
      boots[Math.trunc(0.975 * BOOTSTRAP_ROUNDS) - 1]
    ];
  }

  /* A randomless cross-check on the same differences: normal approximation with the
   * sample standard deviation. Deterministic everywhere, and stated as what it is -
   * an approximation, not the bootstrap. */
  function normalInterval(diffs, meanAdv) {
    var n = diffs.length;
    if (n < 2) return [round2(meanAdv), round2(meanAdv)];
    var squares = diffs.map(function (d) { return (d - meanAdv) * (d - meanAdv); });
    var sd = Math.sqrt(sumOf(squares) / (n - 1));
    var half = 1.96 * sd / Math.sqrt(n);
    return [round2(meanAdv - half), round2(meanAdv + half)];
  }

  function compareMethods(byDay, seed) {
    var s = (seed === undefined || seed === null) ? 1 : Math.trunc(seed);
    var series = compareSeries(byDay);
    var y = series.y;
    var dates = series.dates;
    var n = y.length;
    if (n < MIN_DAYS) {
      return {
        comparable: false, days: n,
        verdict: 'Only ' + n + ' days of history. A method comparison needs at least ' +
                 MIN_DAYS + ', so no method is recommended yet.',
        methods: []
      };
    }

    var start = Math.max(7, Math.trunc(n / 2));
    var points = [];
    for (var t = start; t < n; t++) points.push(t);
    if (points.length < MIN_EVAL_POINTS) {
      return {
        comparable: false, days: n,
        verdict: 'Too few held-out days to rank methods fairly.',
        methods: []
      };
    }

    var errors = {};
    COMPARE_METHODS.forEach(function (entry) {
      errors[entry[0]] = points.map(function (t) {
        return Math.abs(roundHalfEven(entry[1](y, dates, t)) - y[t]);
      });
    });

    var ranked = COMPARE_METHODS.map(function (entry) {
      return { method: entry[0], mae: round2(meanOf(errors[entry[0]])) };
    }).sort(function (a, b) { return a.mae - b.mae; });

    var best = ranked[0].method;
    var runner = ranked[1].method;

    var diffs = [];
    for (var k = 0; k < errors[best].length; k++) diffs.push(errors[runner][k] - errors[best][k]);
    var interval = percentileBootstrap(diffs, s);
    var lo = interval[0];
    var hi = interval[1];
    var meanAdv = meanOf(diffs);
    var distinguishable = lo > 0;

    var verdict;
    if (distinguishable) {
      verdict = "'" + best + "' is the most accurate method here (average miss " +
                pyFixed(ranked[0].mae, 2) + " tickets/day) and its edge over '" + runner +
                "' is larger than chance would explain.";
    } else {
      verdict = "'" + best + "' scored best (" + pyFixed(ranked[0].mae, 2) +
                " tickets/day average miss), but its edge over '" + runner + "' (" +
                pySignedFixed(meanAdv, 2) + " tickets/day) is within what luck alone " +
                'produces on ' + points.length + ' test days. Treat the methods as ' +
                'equally good until there is more history.';
    }

    return {
      comparable: true, days: n, test_days: points.length,
      methods: ranked,
      best: best, runner_up: runner,
      advantage_tickets_per_day: round2(meanAdv),
      interval_95: [round2(lo), round2(hi)],
      interval_95_exact: normalInterval(diffs, meanAdv),
      distinguishable_from_luck: distinguishable,
      verdict: verdict
    };
  }

  /* -------------------------------------------------------------- prioritizer */
  /* Copied from app/prioritizer.py. Wording decides priority, which is exactly the
   * risk the bias audit exists to expose - so the page runs the real lists, not a
   * friendly approximation. */

  var CLINICAL_CONTEXT = ['emergency', 'icu', 'intensive care', 'theatre', 'operating room',
                          'telemetry', 'patient monitor', 'patient bay', 'bedside monitor',
                          'patient monitoring', 'patient care'];
  var CLINICAL_EQUIPMENT = ['ventilator', 'defibrillator', 'patient monitor', 'monitoring terminal',
                            'telemetry', 'infusion pump', 'dialysis', 'crash cart', 'life support',
                            'bedside monitor', 'oxygen'];
  var SAFETY = ['fire', 'flood', 'gas leak', 'power failure', 'outage', 'electrical hazard', 'spill',
                'generator', 'water leak'];
  var URGENT = ['down', 'not working', 'fail', 'keeps disconnect', 'urgent', 'immediately',
                'critical', 'alarm', 'no power', 'offline', 'will not start', 'stopped',
                'rejected', 'cannot log', 'locked out', 'password expired', 'deadline',
                'due tomorrow', 'leaking', 'stopped cooling'];
  var STAFFING_CRITICAL = ['shortage', 'short of', 'short two', 'no staff', 'cover needed',
                           'no cover', 'understaffed', 'cannot fill', 'unfilled shift'];
  var ROUTINE = ['invoice', 'query', 'leave request', 'schedule', 'booking', 'question',
                 'monthly', 'routine', 'annual', 'reminder', 'planning'];

  function anyIn(text, words) {
    for (var i = 0; i < words.length; i++) {
      if (text.indexOf(words[i]) !== -1) return true;
    }
    return false;
  }

  function prioritize(message, sender) {
    var text = (String(message === undefined || message === null ? '' : message) + ' ' +
                (sender === undefined || sender === null ? '' : String(sender))).toLowerCase();
    var score = 0;
    if (anyIn(text, CLINICAL_CONTEXT)) score += 3;
    if (anyIn(text, CLINICAL_EQUIPMENT)) score += 3;
    if (anyIn(text, SAFETY)) score += 4;
    if (anyIn(text, URGENT)) score += 2;
    if (anyIn(text, STAFFING_CRITICAL) && anyIn(text, CLINICAL_CONTEXT)) score += 3;
    if (anyIn(text, ROUTINE)) score -= 2;
    if (text.indexOf('high') !== -1 || text.indexOf('emergency') !== -1) score += 1;
    if (score >= 5) return 'High';
    if (score >= 2) return 'Medium';
    return 'Low';
  }

  /* -------------------------------------------------------------- bias audit */

  var ORDER = { Low: 0, Medium: 1, High: 2, Critical: 3 };

  /* (need, variant A, text A, variant B, text B). A is the variant at risk of being
   * under-served; B is the keyword-rich English the rules were written around. Same
   * six pairs, same wording, as app/bias_audit.MATCHED_PAIRS. */
  var MATCHED_PAIRS = [
    {
      need: 'theatre air conditioning failed',
      a_label: 'plain English',
      a_text: 'theatre aircon failed, surgery list cannot proceed',
      b_label: 'keyword-rich English',
      b_text: 'URGENT: the theatre air conditioning has failed and the surgical list cannot proceed immediately.'
    },
    {
      need: 'low oxygen on a ward',
      a_label: 'plain English',
      a_text: 'ward 4 oxygen tank is almost empty, patients on it',
      b_label: 'keyword-rich English',
      b_text: 'Emergency: critical oxygen supply low in ward 4, patients on oxygen at risk, act asap.'
    },
    {
      need: 'lift out of service',
      a_label: 'Afrikaans',
      a_text: 'Die lift is stukkend en pasiënte kan nie boontoe kom nie, dit is dringend',
      b_label: 'English',
      b_text: 'The lift is broken and patients cannot get upstairs, this is urgent.'
    },
    {
      need: 'dialysis machine down',
      a_label: 'isiZulu',
      a_text: 'Umshini we-dialysis ya-4 awusebenzi, iziguli zilindile, siyadinga usizo ngokushesha',
      b_label: 'English',
      b_text: 'Dialysis machine 4 is not working, patients are waiting, we need help immediately.'
    },
    {
      need: 'fridge holding blood products failing',
      a_label: 'plain English',
      a_text: 'blood fridge is warm and the alarm keeps going off',
      b_label: 'keyword-rich English',
      b_text: 'Critical: the blood bank refrigerator is not working and the temperature alarm is active, urgent.'
    },
    {
      need: 'burst pipe flooding a corridor',
      a_label: 'Afrikaans',
      a_text: "Daar is 'n pyp gebars en die gang is vol water, dit moet nou reggemaak word",
      b_label: 'English',
      b_text: 'A pipe has burst and the corridor is flooded, this must be fixed now.'
    }
  ];

  function pairList(pairs) {
    return (pairs || MATCHED_PAIRS).map(function (p) {
      if (Object.prototype.toString.call(p) === '[object Array]') {
        return { need: p[0], a_label: p[1], a_text: p[2], b_label: p[3], b_text: p[4] };
      }
      return p;
    });
  }

  /* classify(text) -> {priority}. Missing priority reads as "None", as Python's
   * str(dict.get("priority")) does, so a broken classifier is reported not ignored. */
  function priorityOf(result) {
    if (result !== null && typeof result === 'object') {
      var v = result.priority;
      if (v === undefined || v === null) return 'None';
      return String(v);
    }
    return 'None';
  }

  function auditVerdict(rows, inconsistent) {
    if (!rows.length) return 'No pairs supplied.';
    if (!inconsistent.length) {
      return 'Every matched pair received the same priority. No wording bias was detected in this sample.';
    }
    var groups = [];
    inconsistent.forEach(function (r) {
      if (r.under_served && groups.indexOf(r.under_served) === -1) groups.push(r.under_served);
    });
    groups.sort();
    return inconsistent.length + ' of ' + rows.length +
      ' matched pairs received different priority for the same underlying need. ' +
      'The wording that lost out: ' + groups.join(', ') + '. ' +
      'Priority should reflect the situation, not how it was phrased.';
  }

  function runBiasAudit(classify, pairs) {
    var list = pairList(pairs);
    var rows = list.map(function (p) {
      var pa = priorityOf(classify(p.a_text));
      var pb = priorityOf(classify(p.b_text));
      var gap = (ORDER.hasOwnProperty(pb) ? ORDER[pb] : 0) - (ORDER.hasOwnProperty(pa) ? ORDER[pa] : 0);
      return {
        need: p.need,
        variant_a: p.a_label,
        variant_b: p.b_label,
        priority_a: pa,
        priority_b: pb,
        levels_apart: Math.abs(gap),
        under_served: gap > 0 ? p.a_label : (gap < 0 ? p.b_label : null),
        consistent: gap === 0
      };
    });

    var inconsistent = rows.filter(function (r) { return !r.consistent; });
    var byGroup = {};
    var groupOrder = [];
    rows.forEach(function (r) {
      if (!byGroup[r.variant_a]) {
        byGroup[r.variant_a] = { pairs: 0, under_served: 0 };
        groupOrder.push(r.variant_a);
      }
      byGroup[r.variant_a].pairs += 1;
      if (r.under_served === r.variant_a) byGroup[r.variant_a].under_served += 1;
    });

    var worst = 0;
    rows.forEach(function (r) { if (r.levels_apart > worst) worst = r.levels_apart; });

    return {
      pairs_tested: rows.length,
      inconsistent: inconsistent.length,
      consistency_rate: rows.length
        ? round1(100 * (rows.length - inconsistent.length) / rows.length)
        : null,
      worst_gap_levels: worst,
      by_group: byGroup,
      rows: rows,
      verdict: auditVerdict(rows, inconsistent),
      limits: 'Six matched pairs show that a bias exists; they cannot measure how large ' +
              'it is or generalise to every phrasing. A production audit needs far more ' +
              'pairs, written by native speakers, and re-run whenever the rules change.'
    };
  }

  /* ------------------------------------------------------------- decision log */

  /* Signal groups, exactly as app/decision_log.SIGNAL_GROUPS. Names only: the record
   * says WHICH group fired, never which word. */
  var SIGNAL_GROUPS = {
    clinical_context: ['emergency', 'icu', 'intensive care', 'theatre', 'operating room',
                       'telemetry', 'patient monitor', 'patient bay', 'bedside monitor',
                       'patient monitoring', 'patient care'],
    clinical_equipment: ['ventilator', 'defibrillator', 'patient monitor', 'monitoring terminal',
                         'telemetry', 'infusion pump', 'dialysis', 'crash cart', 'life support',
                         'bedside monitor', 'oxygen'],
    safety_hazard: ['fire', 'flood', 'gas leak', 'power failure', 'outage', 'electrical hazard',
                    'spill', 'generator', 'water leak'],
    urgency_words: ['down', 'not working', 'fail', 'urgent', 'immediately', 'critical', 'alarm',
                    'no power', 'offline', 'will not start', 'stopped', 'leaking'],
    routine_words: ['invoice', 'query', 'leave request', 'schedule', 'booking', 'question',
                    'monthly', 'routine', 'annual', 'reminder', 'planning']
  };

  var NON_ASCII_LETTERS = 'áàâäãåéèêëíìîïóòôöõúùûüñçšžœêôûäöü';
  var AFRIKAANS_HINTS = [' die ', ' nie ', ' het ', ' is ', ' dit ', ' van ', ' en ', " 'n "];
  var ZULU_HINTS = ['umshini', 'iziguli', 'ngokushesha', 'usizo', 'awusebenzi', ' ya-', 'ukuthi', 'yini'];

  function signalsFor(text) {
    var t = String(text === undefined || text === null ? '' : text).toLowerCase();
    var out = [];
    var names = Object.keys(SIGNAL_GROUPS);
    for (var i = 0; i < names.length; i++) {
      if (anyIn(t, SIGNAL_GROUPS[names[i]])) out.push(names[i]);
    }
    return out;
  }

  function languageHint(text) {
    var t = ' ' + String(text === undefined || text === null ? '' : text).toLowerCase() + ' ';
    var i;
    for (i = 0; i < ZULU_HINTS.length; i++) {
      if (t.indexOf(ZULU_HINTS[i]) !== -1) return 'likely_isizulu';
    }
    var afrikaans = 0;
    for (i = 0; i < AFRIKAANS_HINTS.length; i++) {
      if (t.indexOf(AFRIKAANS_HINTS[i]) !== -1) afrikaans += 1;
    }
    if (afrikaans >= 2) return 'likely_afrikaans';
    for (i = 0; i < t.length; i++) {
      if (NON_ASCII_LETTERS.indexOf(t.charAt(i)) !== -1) return 'likely_afrikaans';
    }
    return 'english_or_unknown';
  }

  /* UTF-8 bytes, so the hash of a message is the same in every browser and file system
   * regardless of how the page's text was encoded. */
  function utf8Bytes(text) {
    var bytes = [];
    for (var i = 0; i < text.length; i++) {
      var code = text.charCodeAt(i);
      if (code >= 0xd800 && code <= 0xdbff && i + 1 < text.length) {
        var low = text.charCodeAt(i + 1);
        if (low >= 0xdc00 && low <= 0xdfff) {
          code = 0x10000 + ((code - 0xd800) << 10) + (low - 0xdc00);
          i += 1;
        }
      }
      if (code < 0x80) {
        bytes.push(code);
      } else if (code < 0x800) {
        bytes.push(0xc0 | (code >> 6), 0x80 | (code & 0x3f));
      } else if (code < 0x10000) {
        bytes.push(0xe0 | (code >> 12), 0x80 | ((code >> 6) & 0x3f), 0x80 | (code & 0x3f));
      } else {
        bytes.push(0xf0 | (code >> 18), 0x80 | ((code >> 12) & 0x3f),
                   0x80 | ((code >> 6) & 0x3f), 0x80 | (code & 0x3f));
      }
    }
    return bytes;
  }

  function fnv1a(bytes, seed, reverse) {
    var h = seed >>> 0;
    var step = reverse ? -1 : 1;
    var start = reverse ? bytes.length - 1 : 0;
    for (var i = 0; i < bytes.length; i++) {
      h = (h ^ bytes[start + i * step]) >>> 0;
      h = Math.imul(h, 16777619) >>> 0;
    }
    return ('00000000' + h.toString(16)).slice(-8);
  }

  /* A short fingerprint for de-duplication, NOT Python's value.
   *
   * app/decision_log.py stores sha256(message)[:12]. Reproducing SHA-256 in the page
   * would be possible but pointless: the browser log and the service log are separate
   * append-only stores, nothing compares their hashes, and the property that matters -
   * the same message always produces the same short token, and the token reveals
   * nothing about the words - is met by two FNV-1a passes over the UTF-8 bytes.
   * Do NOT expect these to match Python's; scripts/check_governance_parity.mjs asserts
   * only that they are 12 hex characters and stable.
   */
  function fingerprint(text) {
    var stem = String(text === undefined || text === null ? '' : text).trim().toLowerCase();
    var bytes = utf8Bytes(stem);
    return (fnv1a(bytes, 0x811c9dc5, false) + fnv1a(bytes, 0x01000193, true)).slice(0, 12);
  }

  /* Python str() of an attribute that may be missing (-> "") or None (-> "None"). */
  function attrStr(obj, key) {
    if (obj === null || obj === undefined) return '';
    if (!(key in Object(obj))) return '';
    var v = obj[key];
    if (v === null || v === undefined) return 'None';
    return String(v);
  }

  function attrOrNull(obj, key) {
    if (obj === null || obj === undefined) return null;
    var v = obj[key];
    return (v === undefined) ? null : v;
  }

  /* Same shape as Python's datetime.now(timezone.utc).isoformat(timespec="seconds"). */
  function isoSecondsUtc(date) {
    return date.toISOString().slice(0, 19) + '+00:00';
  }

  function buildDecisionRecord(message, ticket, at) {
    var text = message === undefined || message === null ? '' : String(message);
    var sig = signalsFor(text);
    var lang = languageHint(text);
    var review = lang !== 'english_or_unknown' && sig.indexOf('urgency_words') === -1;
    return {
      at: at || isoSecondsUtc(new Date()),
      ticket_id: attrOrNull(ticket, 'ticket_id'),
      category: attrStr(ticket, 'category'),
      priority: attrStr(ticket, 'priority'),
      assigned_to: attrOrNull(ticket, 'assigned_to'),
      signals_fired: sig,
      language_hint: lang,
      message_fingerprint: fingerprint(text),
      // Python len(str) counts code points; Array.from does the same, where
      // String.length would count UTF-16 units and over-count non-BMP characters.
      message_length: Array.from(text).length,
      needs_bias_review: review,
      note: review
        ? 'Non-English wording and no urgency signal fired: priority may under-state ' +
          'need. A person should confirm it.'
        : ''
    };
  }

  /* Pure over an array of records: the page keeps its log in localStorage, so nothing
   * here touches a file. app/decision_log.transparency_note() summarises read_log()
   * through the same logic, which is what the parity check compares against. */
  function transparencyNote(rows) {
    var list = rows || [];
    var n = list.length;
    if (!n) return { decisions: 0, note: 'No decisions have been logged yet.' };
    var flagged = 0;
    var nonEnglish = 0;
    var byPriority = {};
    list.forEach(function (r) {
      if (r.needs_bias_review) flagged += 1;
      if (r.language_hint !== 'english_or_unknown') nonEnglish += 1;
      var p = r.priority;
      byPriority[p] = (byPriority[p] || 0) + 1;
    });
    return {
      decisions: n,
      by_priority: byPriority,
      non_english_messages: nonEnglish,
      flagged_for_bias_review: flagged,
      note: n + ' automated decisions logged. ' + flagged +
        ' were flagged because the message looked non-English and no urgency signal ' +
        'fired, which is the pattern the bias audit found under-prioritises need. The ' +
        'log stores no message text, only category, priority, which signal groups fired ' +
        'and a short fingerprint.',
      limits: 'Language is a cheap hint, not a detector, so counts are approximate. ' +
              'The flag asks a person to look; it does not change the priority.'
    };
  }

  root.MedOpsGovernance = {
    // numbers
    roundHalfEven: roundHalfEven,
    mulberry32: mulberry32,
    // forecast
    forecastVolume: forecastVolume,
    compareMethods: compareMethods,
    MIN_DAYS: MIN_DAYS,
    BOOTSTRAP_ROUNDS: BOOTSTRAP_ROUNDS,
    // priority + bias
    prioritize: prioritize,
    MATCHED_PAIRS: MATCHED_PAIRS,
    ORDER: ORDER,
    runBiasAudit: runBiasAudit,
    // decision log
    SIGNAL_GROUPS: SIGNAL_GROUPS,
    signalsFor: signalsFor,
    languageHint: languageHint,
    fingerprint: fingerprint,
    buildDecisionRecord: buildDecisionRecord,
    transparencyNote: transparencyNote,
    isoSecondsUtc: isoSecondsUtc
  };
})(typeof window !== 'undefined' ? window : globalThis);
