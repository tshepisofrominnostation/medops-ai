/* The Week 3 module: ticket store, lifecycle, reply drafting and the weekly summary.
 *
 * Everything here works on one documented record shape (docs/DATA_MODEL.md) so a ticket
 * has the same fields whether it was created in this page, by the API, or read back from
 * data/demo_tickets.json. The numbers come from web/analytics.js, which is parity-tested
 * against app/analytics.py; this file only decides what to say about them.
 */
(function (root) {
  'use strict';

  var A = root.MedOpsAnalytics;
  var S = root.MedOpsSemantic;
  var KEY = 'medops.week3.store.v1';
  var ID_KEY = 'medops.week3.nextid.v1';

  /* Routing comes from app/assigner.py via the bundle: a hand-typed copy of a
   * department list is how a ticket ends up in a queue nobody watches. */
  var ASSIGN = {};
  function configure(bundle) {
    if (bundle && bundle.rules) ASSIGN = bundle.rules.assign;
  }

  /* ---- store ------------------------------------------------------------- */

  function nowIso() { return new Date().toISOString(); }

  function load() {
    try {
      var raw = root.localStorage && root.localStorage.getItem(KEY);
      if (!raw) return [];
      var parsed = JSON.parse(raw);
      return Array.isArray(parsed) ? parsed : [];
    } catch (e) { return []; }
  }

  function save(rows) {
    try { root.localStorage.setItem(KEY, JSON.stringify(rows)); } catch (e) { /* private mode */ }
    return rows;
  }

  function nextId(rows) {
    var stored = 0;
    try { stored = parseInt(root.localStorage.getItem(ID_KEY) || '0', 10) || 0; } catch (e) { stored = 0; }
    var highest = rows.reduce(function (n, r) {
      var m = /MED-(\d+)/.exec(r.ticket_id || '');
      return m ? Math.max(n, parseInt(m[1], 10)) : n;
    }, stored);
    var next = highest + 1;
    try { root.localStorage.setItem(ID_KEY, String(next)); } catch (e) { /* ignore */ }
    return 'MED-' + String(next).padStart(3, '0');
  }

  function clearStore() {
    try {
      root.localStorage.removeItem(KEY);
      root.localStorage.removeItem(ID_KEY);
    } catch (e) { /* ignore */ }
  }

  /* ---- classification + reply ------------------------------------------- */

  function senderOf(text) {
    var m = /[-–]\s*((?:Dr|Prof|Sr|Sister|Nurse|Mr|Mrs|Ms)\.?\s+[A-Z][\w'’-]*(?:\s+[A-Z][\w'’-]*)?)\s*(?:\(([^)]+)\))?\s*$/
      .exec(text || '');
    if (!m) return { sender: 'Unspecified hospital staff', ward: '' };
    return { sender: m[1], ward: m[2] || '' };
  }

  /* Priority is the service's rule (app/prioritizer.py), evaluated in the browser.
   * Sender and ward are part of the text, as they are in Python. */
  function priorityOf(text, sender) {
    return S.decidePriority(text, sender || '');
  }

  var REPLY = {
    'IT & Medical Tech': {
      high: function (a, t, l) {
        return a + ' has been activated for ' + t + ' at ' + l + '. Do not use the affected equipment for patient care until biomedical engineering has cleared it. If the situation changes, escalate to the on-call coordinator immediately.';
      },
      normal: function (a, t) { return a + ' has received ' + t + ' and will restore the affected system, then confirm your access.'; }
    },
    HR: {
      high: function (a, t) { return a + ' is sourcing cover now for ' + t + '. The relevant manager will be called with confirmation within the hour, so do not leave the roster unconfirmed before handover.'; },
      normal: function (a, t) { return a + ' has received ' + t + ' and will process the request, then confirm the details with you.'; }
    },
    Finance: {
      high: function (a, t) { return a + ' is processing ' + t + ' as an urgent payment. Confirm the supplier hold in writing while the release is completed.'; },
      normal: function (a, t) { return a + ' has received ' + t + ' and will review the account, then confirm the outcome.'; }
    },
    Operations: {
      high: function (a, t, l) { return a + ' is responding to ' + t + ' at ' + l + '. Keep the affected area clear until the duty manager confirms it is safe, and escalate immediately if anyone is at risk.'; },
      normal: function (a, t) { return a + ' has received ' + t + ' and will schedule the work, then confirm the crew and the date.'; }
    }
  };

  var WINDOW = { High: '15 minutes', Medium: 'one working day', Low: 'two working days' };

  function locationOf(text) {
    var m = /\b(?:in|at|outside|near)\s+((?:the\s+)?(?:ICU|theatre|ward|bay|cubicle|corridor|kitchen|block|reception|casualty|maternity|pharmacy|radiology|lab)[\w\s'-]{0,22})/i.exec(text || '');
    return m ? m[1].trim().replace(/\s+/g, ' ') : 'the affected area';
  }

  /* Draft the reply, and log what produced it so the record is auditable. */
  var REQUESTABLE_TONES = ['formal', 'friendly', 'urgent'];

  /* Week 2 tone control. A requested tone changes courtesy, never facts: the ticket
     id, the assigned team and the response window are identical in all three. */
  function draftReply(ticket, requested) {
    var detected = S.tone(ticket.raw_message || '');
    var bank = REPLY[ticket.category] || REPLY.Operations;
    var loc = locationOf(ticket.raw_message);
    var window = WINDOW[ticket.priority] || 'two working days';
    var tid = ticket.ticket_id, team = ticket.assigned_to;

    if (requested && REQUESTABLE_TONES.indexOf(requested) === -1) {
      throw new Error('unsupported tone: ' + requested);
    }
    if (requested === 'urgent') {
      return { draft: bank.high(team, tid, loc), tone: 'urgent', requested: true,
               tone_evidence: detected.evidence, engine: 'template (requested tone)', generated_at: nowIso() };
    }
    if (requested === 'formal') {
      return { draft: 'Please be advised that ' + tid + ' has been received and assigned to ' + team +
               '. An update is to be expected within ' + window + '; written confirmation will follow upon completion. ' +
               'Kindly append any further detail to this ticket reference.',
               tone: 'formal', requested: true, tone_evidence: detected.evidence,
               engine: 'template (requested tone)', generated_at: nowIso() };
    }
    if (requested === 'friendly') {
      return { draft: "Thanks for flagging this. " + tid + ' is with ' + team + " now and they'll sort it. " +
               "You'll hear from us within " + window + ", and we'll confirm in writing once it's done. " +
               'If anything changes, just reply here with ' + tid + '.',
               tone: 'friendly', requested: true, tone_evidence: detected.evidence,
               engine: 'template (requested tone)', generated_at: nowIso() };
    }

    // No tone requested: historical behaviour, unchanged.
    var body = ticket.priority === 'High' ? bank.high(team, tid, loc) : bank.normal(team, tid);
    var opener = detected.tone === 'friendly' ? 'Thank you for reaching out. ' : 'Thank you for logging this. ';
    var closing = ticket.priority === 'High' ? '' : ' Expect an update within ' + window + '.';
    return {
      draft: opener + body + closing,
      tone: detected.tone,
      tone_evidence: detected.evidence,
      engine: 'semantic-tfidf → signals → template',
      generated_at: nowIso()
    };
  }

  /* ---- create ------------------------------------------------------------ */

  function create(msg, opts) {
    opts = opts || {};
    var text = String(msg || '').trim();
    if (!text) throw new Error('nothing to classify');

    var sender = senderOf(text);
    if (opts.sender) sender.sender = opts.sender;

    var decision = S.decide(text);
    var prio = priorityOf(text, sender.sender + ' ' + sender.ward);
    var screen = S.phiScan(text);
    var category = decision.category;

    var rows = load();
    var ticket = {
      ticket_id: nextId(rows),
      timestamp: nowIso(),
      sender: sender.sender,
      ward: sender.ward,
      category: category,
      priority: prio.priority,
      // The summary is stored redacted; the raw text is kept in this browser only,
      // and marked, because the reply needs it and the user needs to see it.
      summary: (S.phiRedact(text).slice(0, 220) || '(no description)') +
        ' Reported by ' + (sender.ward || 'hospital staff') + '; classified as ' + category +
        ' with ' + prio.priority + ' priority.',
      assigned_to: ASSIGN[category][prio.priority],
      status: 'Open',
      ai_response: {},
      signals: {
        // How the category was decided, and what the other layer thought of it.
        decided_by: decision.source,
        rule_category: decision.rule.category,
        rule_confidence: decision.rule.confidence,
        rule_matched: decision.rule.matched,
        semantic_category: decision.semantic.category,
        semantic_confidence: decision.semantic.similarity,
        semantic_agrees: decision.agree,
        unsure: decision.unsure,
        priority_score: prio.score,
        priority_signals: prio.signals,
        phi_blocked: screen.blocked,
        phi_flags: screen.flags.map(function (f) { return f.rule; }),
        matched: S.nearest(text, 3)
      }
    };

    // An urgent clinical request is answered on creation, so first_response_at is the
    // moment the draft exists — which is what makes response times measurable at all.
    if (opts.respondNow !== false) {
      ticket.status = 'In Progress';
      ticket.first_response_at = nowIso();
      ticket.ai_response = draftReply(Object.assign({}, ticket, { raw_message: text }));
    }
    ticket.raw_message = text;

    rows.push(ticket);
    save(rows);
    return ticket;
  }

  /* ---- lifecycle (mirrors app/lifecycle.update_ticket) ------------------- */

  function update(ticketId, status, at) {
    var rows = load();
    var ticket = rows.filter(function (r) { return r.ticket_id === ticketId; })[0];
    if (!ticket) throw new Error('unknown ticket ' + ticketId);
    if (['Open', 'In Progress', 'Resolved'].indexOf(status) === -1) throw new Error('bad status');
    var stamp = at || nowIso();
    if (Date.parse(stamp) < Date.parse(ticket.timestamp)) {
      throw new Error('a lifecycle timestamp cannot be earlier than ticket creation');
    }
    if (status === 'In Progress') {
      if (!ticket.first_response_at) ticket.first_response_at = stamp;
      delete ticket.resolved_at;
    } else if (status === 'Resolved') {
      if (!ticket.first_response_at) ticket.first_response_at = stamp;
      ticket.resolved_at = stamp;
    } else {
      delete ticket.resolved_at;
    }
    ticket.status = status;
    save(rows);
    return ticket;
  }

  /* ---- weekly summary ---------------------------------------------------- */

  function pct(x) { return x === null || x === undefined ? 'n/a' : Math.round(x * 100) + '%'; }
  function mins(m) {
    if (m === null || m === undefined) return 'not measurable yet';
    if (m < 60) return Math.round(m) + ' min';
    var h = Math.floor(m / 60), rest = Math.round(m % 60);
    return h + ' h' + (rest ? ' ' + rest + ' min' : '');
  }

  function shift(x) {
    if (x === null || x === undefined || x === 0) return 'unchanged';
    return (x > 0 ? '+' : '') + Math.round(x * 100) + '%';
  }

  /* Findings are computed, never phrased by a model: each one carries the numbers it
   * rests on, and says when the sample is too small to support a claim. */
  function weeklySummary(rows, win) {
    win = win || A.weekWindow(rows);
    var cur = A.buildAnalytics(rows, win.start, win.end);
    var prevWin = A.shiftWindow(win, 7);
    var prev = A.buildAnalytics(rows, prevWin.start, prevWin.end);

    var findings = [];
    var enoughForTrend = cur.total_tickets >= 8;
    var delta = cur.total_tickets - prev.total_tickets;
    var deltaPct = prev.total_tickets ? delta / prev.total_tickets : null;

    findings.push({
      kind: 'volume',
      title: 'Volume ' + (delta === 0 ? 'held steady' : (delta > 0 ? 'rose' : 'fell')) +
        ' at ' + cur.total_tickets + ' tickets',
      detail: enoughForTrend
        ? cur.total_tickets + ' tickets this week against ' + prev.total_tickets +
          ' the week before (' + shift(deltaPct) + '), ' + (cur.rates.tickets_per_day) +
          ' per day on average.'
        : 'Only ' + cur.total_tickets + ' tickets in this window, so week-on-week comparison is not yet meaningful; treat the trend as provisional.',
      evidence: { this_week: cur.total_tickets, last_week: prev.total_tickets, delta_pct: deltaPct },
      thin_data: !enoughForTrend
    });

    // Busiest department.
    var depts = Object.keys(cur.by_department).map(function (k) { return [k, cur.by_department[k]]; })
      .sort(function (a, b) { return b[1] - a[1]; });
    if (depts.length) {
      var top = depts[0];
      // A tie is a tie: reporting one of two equal queues as the winner would be wrong.
      var tied = depts.filter(function (d) { return d[1] === top[1] && d[0] !== top[0]; });
      findings.push({
        kind: 'department',
        title: tied.length
          ? top[0] + ' tied for the highest load (' + top[1] + ' tickets each)'
          : top[0] + ' carried the highest load (' + top[1] + ' tickets)',
        detail: top[0] + ' received ' + top[1] + ' of ' + cur.total_tickets + ' tickets (' +
          pct(top[1] / cur.total_tickets) + '). ' +
          (tied.length
            ? tied.map(function (d) { return d[0]; }).join(' and ') + ' received the same number.'
            : (depts[1] ? depts[1][0] + ' followed with ' + depts[1][1] + '.' : 'No other department had volume.')),
        evidence: { by_department: cur.by_department },
        thin_data: false
      });
    }

    // Category mix change.
    var catChanges = A.CATEGORIES().map(function (c) {
      return { category: c, now: cur.by_category[c] || 0, before: prev.by_category[c] || 0 };
    }).filter(function (r) { return r.now !== r.before; })
      .sort(function (a, b) { return Math.abs(b.now - b.before) - Math.abs(a.now - a.before); });
    if (catChanges.length) {
      var c0 = catChanges[0];
      findings.push({
        kind: 'category',
        title: c0.category + ' ' + (c0.now > c0.before ? 'rose' : 'fell') + ' to ' + c0.now,
        detail: 'The largest shift in mix was ' + c0.category + ': ' + c0.before + ' last week, ' +
          c0.now + ' this week (' + (c0.now - c0.before > 0 ? '+' : '') + (c0.now - c0.before) + ').',
        evidence: { changes: catChanges },
        thin_data: !enoughForTrend
      });
    }

    // Response time against the stated targets.
    var sla = cur.sla;
    if (sla.measured_tickets) {
      var attainment = sla.attainment;
      findings.push({
        kind: 'sla',
        title: 'First response met target on ' + pct(attainment) + ' of measured tickets',
        detail: 'Measured on ' + sla.measured_tickets + ' tickets with a recorded first response. ' +
          'Median first response was ' + mins(cur.response_time.median_minutes) + '; the slowest was ' +
          mins(cur.response_time.worst_minutes) + '. Targets: High ' + mins(sla.targets_minutes.High) +
          ', Medium ' + mins(sla.targets_minutes.Medium) + ', Low ' + mins(sla.targets_minutes.Low) +
          '. These are proposed internal targets, not hospital policy.',
        evidence: { attainment: attainment, median_minutes: cur.response_time.median_minutes, by_priority: sla.by_priority },
        thin_data: sla.measured_tickets < 5,
        severity: attainment === null ? 'unknown' : (attainment >= 0.9 ? 'ok' : (attainment >= 0.7 ? 'watch' : 'act'))
      });
    } else {
      findings.push({
        kind: 'sla',
        title: 'No response times to measure yet',
        detail: 'A response time exists once a draft reply has been logged against a ticket. ' +
          'None of the ' + cur.total_tickets + ' tickets in this window has one.',
        evidence: { measured: 0 },
        thin_data: true,
        severity: 'unknown'
      });
    }

    // Backlog, and the oldest thing in it.
    var openRows = rows.filter(function (r) { return A.statusOf(r) !== 'Resolved'; });
    var oldest = openRows.slice().sort(function (a, b) {
      return Date.parse(a.timestamp) - Date.parse(b.timestamp);
    })[0];
    if (openRows.length) {
      findings.push({
        kind: 'backlog',
        title: openRows.length + ' ticket' + (openRows.length === 1 ? '' : 's') + ' still open',
        detail: (oldest ? 'The oldest is ' + oldest.ticket_id + ' (' + oldest.priority + ', ' +
          oldest.category + ') logged ' + oldest.timestamp.slice(0, 10) +
          ', now ' + Math.round((Date.now() - Date.parse(oldest.timestamp)) / 86400000) + ' days old. ' : '') +
          (openRows.filter(function (r) { return r.priority === 'High'; }).length
            ? openRows.filter(function (r) { return r.priority === 'High'; }).length +
              ' of them are High priority.'
            : 'None of them is High priority.'),
        evidence: { open: openRows.length, oldest: oldest ? oldest.ticket_id : null },
        thin_data: false,
        severity: oldest && oldest.priority === 'High' ? 'watch' : 'ok'
      });
    }

    var headline = cur.total_tickets + ' tickets from ' + win.start + ' to ' + win.end + '. ' +
      (sla.attainment !== null ? pct(sla.attainment) + ' of measured tickets got a first response inside target. ' : '') +
      (depts.length ? depts[0][0] + ' was the busiest queue. ' : '') +
      (openRows.length ? openRows.length + ' remain open.' : 'Nothing is open.');

    return {
      window: win,
      previous_window: prevWin,
      analytics: cur,
      previous: prev,
      headline: headline,
      findings: findings,
      thin_windows: !enoughForTrend,
      generated_at: nowIso()
    };
  }

  root.MedOpsApp = {
    configure: configure,
    load: load,
    save: save,
    clearStore: clearStore,
    create: create,
    update: update,
    draftReply: draftReply,
    priorityOf: priorityOf,
    senderOf: senderOf,
    weeklySummary: weeklySummary,
    ASSIGN: ASSIGN
  };
})(typeof window !== 'undefined' ? window : globalThis);
