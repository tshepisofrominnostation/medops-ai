/* Page wiring. Rendering only: every number comes from web/analytics.js, every label
 * from web/semantic.js, every record from web/app.js. */
(function () {
  'use strict';

  var A = window.MedOpsAnalytics;
  var S = window.MedOpsSemantic;
  var APP = window.MedOpsApp;
  var bundle = JSON.parse(document.getElementById('bundle').textContent);

  A.configure(bundle.taxonomy);
  S.init(bundle);
  APP.configure(bundle);

  var $ = function (id) { return document.getElementById(id); };
  var esc = function (s) {
    return String(s === null || s === undefined ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  };
  var num = function (n) { return n === null || n === undefined ? '–' : String(n); };
  var pct = function (x) { return x === null || x === undefined ? '–' : Math.round(x * 100) + '%'; };
  var prioClass = function (p) { return p === 'High' ? 'hi' : (p === 'Medium' ? 'med' : 'low'); };

  /* One store, seeded once from the committed history. Logging a ticket appends to it
   * rather than replacing the view: a dashboard that forgets 103 tickets the moment you
   * add one is not tracking anything. */
  var SEED = JSON.parse(JSON.stringify(bundle.store));
  function seedIfEmpty() {
    var key = 'medops.week3.store.v1';
    var present = false;
    try { present = window.localStorage.getItem(key) !== null; } catch (e) { present = false; }
    if (!present) APP.save(JSON.parse(JSON.stringify(SEED)));
  }
  function rows() { return APP.load(); }
  function usingSeed() { return rows().length === SEED.length; }

  var SAMPLES = [
    'The patient monitoring terminal in Bay 3 keeps disconnecting mid-surgery. This is unacceptable, we nearly lost a patient. Dr. S. Khumalo (Emergency Ward)',
    'Ventilator will not start in ICU, alarm is going off, patient is on it now - Sr. Naidoo (ICU)',
    'Please can you check why my payslip shows no overtime for October - Mr. J. Mokoena (Theatre)',
    'Water leak in the corridor outside maternity, the floor is flooding - Sr. Pillay (Maternity)',
    'Invoice from MedSupply is double what we agreed, R48 000 instead of R24 000 - Ms. N. Dube (Finance)',
    'Roster for December is still not published and staff are threatening to strike - Mr. T. Sithole (HR)'
  ];

  /* ---- tab 1: submit ---------------------------------------------------- */

  function renderQuick() {
    $('quick').innerHTML = SAMPLES.map(function (s, i) {
      var short = s.length > 52 ? s.slice(0, 52).replace(/\s+\S*$/, '') + '…' : s;
      return '<button class="btn2 tiny" data-sample="' + i + '">' + esc(short) + '</button>';
    }).join('');
  }

  function submit() {
    var text = $('msg').value.trim();
    if (!text) { $('hint').textContent = 'Type or paste a request first.'; return; }
    var ticket;
    try {
      ticket = APP.create(text);
    } catch (e) {
      $('hint').textContent = 'Could not classify that: ' + e.message;
      return;
    }
    $('hint').textContent = 'Logged as ' + ticket.ticket_id + ' in this browser.';
    renderTicket(ticket);
    renderAll();
  }

  function renderTicket(t) {
    $('result').classList.remove('hide');
    var sig = t.signals || {};
    var unsure = sig.unsure;
    var chips =
      '<span class="chip cat">' + esc(t.category) + (unsure ? ' (unsure)' : '') + '</span>' +
      '<span class="chip ' + prioClass(t.priority) + '">' + esc(t.priority) + ' priority</span>' +
      '<span class="chip neutral">' + esc(t.assigned_to) + '</span>' +
      '<span class="chip neutral">' + esc(t.status) + '</span>' +
      (sig.phi_blocked ? '<span class="chip warn">patient data redacted</span>' : '');

    var why = [];
    if (sig.decided_by === 'rules') {
      why.push('<b>Why this category:</b> the routing rules matched ' +
        (sig.rule_matched && sig.rule_matched.length
          ? '\u201c' + esc(sig.rule_matched.slice(0, 5).join('\u201d, \u201c')) + '\u201d'
          : 'weighted keywords') +
        ', giving ' + esc(t.category) + ' ' + pct(sig.rule_confidence) + ' of the keyword weight. ' +
        (sig.semantic_agrees
          ? 'The trained classifier independently agreed.'
          : 'The trained classifier leaned ' + esc(sig.semantic_category) + ' instead (' +
            (sig.semantic_confidence || 0).toFixed(2) + '), so this one is worth a human glance.'));
    } else if (sig.decided_by === 'semantic') {
      why.push('<b>Why this category:</b> no routing keyword matched, so the trained classifier decided ' +
        esc(t.category) + ' on ' + (sig.semantic_confidence || 0).toFixed(2) + ' cosine similarity.');
    } else {
      why.push('<b>Why this category:</b> nothing in the wording pointed anywhere, so it defaults to ' +
        esc(t.category) + '. Treat it as a guess and re-route it.');
    }
    if (sig.matched && sig.matched.length) {
      why.push('<b>Closest stored examples:</b> ' + sig.matched.map(function (m) {
        return '\u201c' + esc(m.text.slice(0, 64)) + '\u2026\u201d (' + esc(m.category) + ', ' +
          m.similarity.toFixed(2) + ')';
      }).join('; ') + '.');
    }
    if (sig.priority_signals && sig.priority_signals.length) {
      why.push('<b>Why this priority:</b> ' + sig.priority_signals.map(function (x) {
        return esc(x.signal) + ' (' + (x.weight > 0 ? '+' : '') + x.weight + ')';
      }).join('; ') + '. Score ' + sig.priority_score + ' (5 and above is High, 2 and above Medium).');
    } else {
      why.push('<b>Why this priority:</b> no urgency signal fired, so it defaults to Low.');
    }
    if (sig.phi_flags && sig.phi_flags.length) {
      why.push('<b>Patient-data screen:</b> flagged ' + esc(sig.phi_flags.join(', ')) +
        '. The stored summary is redacted; the identifiers never enter the record.');
    }

    $('verdict').innerHTML = '<div>' + chips + '</div><p class="small muted" style="margin-top:8px">' +
      why.join(' ') + '</p>';

    var ai = t.ai_response || {};
    $('replybox').innerHTML =
      '<div class="card" style="background:var(--panel2);margin:0">' +
      '<h3>Drafted reply <span class="tiny muted">(' + esc(ai.tone || 'formal') + ' tone · ' + esc(ai.engine || '') + ')</span></h3>' +
      '<p style="margin:8px 0 0">' + esc(ai.draft || 'No reply drafted.') + '</p></div>';

    var stored = Object.assign({}, t);
    delete stored.raw_message;
    $('json').textContent = JSON.stringify(stored, null, 2);
  }

  function renderLog() {
    var list = APP.load();
    var added = list.length - SEED.length;
    $('logmeta').textContent = list.length + ' tickets in this browser' +
      (added > 0 ? ' (' + added + ' of them yours, the rest sample history)' : ' (the committed sample history)') +
      ' · stored here, not on a server.';
    if (!list.length) {
      $('log').innerHTML = '<p class="empty">No tickets in this browser. Reload to restore the sample history.</p>';
      return;
    }
    var ordered = list.slice().sort(function (a, b) { return Date.parse(b.timestamp) - Date.parse(a.timestamp); });
    var rowsHtml = ordered.slice(0, 12).map(function (t) {
      var mins = A.responseMinutes(t);
      return '<tr>' +
        '<td class="mono">' + esc(t.ticket_id) + '</td>' +
        '<td><span class="chip cat" style="margin:0">' + esc(t.category) + '</span></td>' +
        '<td><span class="chip ' + prioClass(t.priority) + '" style="margin:0">' + esc(t.priority) + '</span></td>' +
        '<td>' + esc(t.sender) + '</td>' +
        '<td>' + esc(t.status) + '</td>' +
        '<td class="muted">' + (mins === null ? '–' : Math.round(mins) + ' min') + '</td>' +
        '<td class="row" style="gap:6px">' +
        (t.status !== 'Resolved'
          ? '<button class="linkbtn" data-resolve="' + esc(t.ticket_id) + '">resolve</button>'
          : '<button class="linkbtn" data-reopen="' + esc(t.ticket_id) + '">reopen</button>') +
        '</td></tr>';
    }).join('');
    $('log').innerHTML = '<table><thead><tr><th>Ticket</th><th>Category</th><th>Priority</th><th>Sender</th>' +
      '<th>Status</th><th>First response</th><th></th></tr></thead><tbody>' + rowsHtml + '</tbody></table>';
  }

  /* ---- tab 2: dashboard ------------------------------------------------- */

  var windowMode = '7';

  function windowFor(list) {
    if (windowMode === 'all') return { start: null, end: null, label: 'All time' };
    var days = parseInt(windowMode, 10);
    var w = A.weekWindow(list, null, days);
    return { start: w.start, end: w.end, label: days === 7 ? 'This week' : 'Last ' + days + ' days' };
  }

  function kpi(label, value, note) {
    return '<div class="kpi"><div class="label">' + esc(label) + '</div>' +
      '<div class="value">' + esc(value) + '</div>' +
      (note ? '<div class="note">' + esc(note) + '</div>' : '') + '</div>';
  }

  function bars(entries, unit) {
    var max = Math.max.apply(null, entries.map(function (e) { return e.value; }).concat([1]));
    return entries.map(function (e) {
      var width = Math.max(2, Math.round((e.value / max) * 100));
      return '<div class="dept"><span class="name">' + esc(e.label) + '</span>' +
        '<span class="val">' + esc(e.value) + (unit || '') + '</span>' +
        '<span class="track"><span class="bar" style="display:block;width:' + width + '%"></span></span></div>';
    }).join('');
  }

  function renderDash() {
    var list = rows();
    var win = windowFor(list);
    var a = A.buildAnalytics(list, win.start, win.end);
    var prev = win.start ? A.buildAnalytics(list, A.shiftWindow({ start: win.start, end: win.end }, 7).start,
      A.shiftWindow({ start: win.start, end: win.end }, 7).end) : null;

    $('dashwindow').textContent = (win.start ? win.start + ' to ' + win.end : 'every stored ticket') +
      ' · ' + list.length + ' tickets in this browser' +
      (usingSeed() ? ' (sample history)' : ' (sample history plus yours)');

    var deltaNote = prev && prev.total_tickets
      ? (a.total_tickets - prev.total_tickets >= 0 ? '+' : '') +
        Math.round((a.total_tickets - prev.total_tickets) / prev.total_tickets * 100) + '% vs previous week'
      : 'no comparable week';

    $('kpis').innerHTML =
      kpi('Tickets', num(a.total_tickets), deltaNote) +
      kpi('Median first response', a.response_time.median_minutes === null ? '–' : Math.round(a.response_time.median_minutes) + ' min',
        a.response_time.measured_tickets + ' of ' + a.total_tickets + ' measured') +
      kpi('On target', pct(a.sla.attainment), a.sla.measured_tickets + ' tickets with a response') +
      kpi('Open now',
        num(list.filter(function (r) { return A.statusOf(r) !== 'Resolved'; }).length),
        list.filter(function (r) { return A.statusOf(r) === 'Resolved'; }).length + ' resolved in total');

    $('deptchart').innerHTML = bars(Object.keys(a.by_department).map(function (k) {
      return { label: k, value: a.by_department[k] };
    }));

    $('catchart').innerHTML = bars(A.CATEGORIES().map(function (c) {
      return { label: c, value: a.by_category[c] || 0 };
    }));

    var targets = a.sla.targets_minutes;
    $('slachart').innerHTML = A.PRIORITIES().map(function (p) {
      var mean = a.response_time.by_priority[p];
      var target = targets[p];
      var hit = a.sla.by_priority[p];
      var ratio = mean === null ? 0 : Math.min(100, Math.round(mean / (target * 2) * 100));
      return '<div class="dept"><span class="name">' + esc(p) + ' priority</span>' +
        '<span class="val">' + (mean === null ? 'not measured' : Math.round(mean) + ' min · target ' + target + ' min · ' + pct(hit) + ' met') + '</span>' +
        '<span class="track"><span class="bar" style="display:block;width:' + ratio + '%;background:' +
        (mean === null ? '#334155' : (mean <= target ? '#22d3ee' : '#f59e0b')) + '"></span></span></div>';
    }).join('');

    var inWindow = list.filter(function (r) {
      if (!win.start) return true;
      var d = A.recordDate(r);
      return d && d >= win.start && d <= win.end;
    }).sort(function (x, y) { return Date.parse(y.timestamp) - Date.parse(x.timestamp); });

    $('dashtable').innerHTML = inWindow.length
      ? '<table><thead><tr><th>Ticket</th><th>Logged</th><th>Category</th><th>Priority</th><th>Department</th>' +
        '<th>Status</th><th>Response</th></tr></thead><tbody>' +
        inWindow.slice(0, 25).map(function (t) {
          var m = A.responseMinutes(t);
          return '<tr><td class="mono">' + esc(t.ticket_id) + '</td>' +
            '<td class="muted">' + esc((t.timestamp || '').slice(0, 10)) + '</td>' +
            '<td>' + esc(t.category) + '</td>' +
            '<td><span class="chip ' + prioClass(t.priority) + '" style="margin:0">' + esc(t.priority) + '</span></td>' +
            '<td class="muted">' + esc(t.assigned_to) + '</td>' +
            '<td>' + esc(A.statusOf(t)) + '</td>' +
            '<td class="muted">' + (m === null ? '–' : Math.round(m) + ' min') + '</td></tr>';
        }).join('') + '</tbody></table>' +
        (inWindow.length > 25 ? '<p class="small muted" style="margin-top:8px">Showing 25 of ' + inWindow.length + '.</p>' : '')
      : '<p class="empty">No tickets in this window.</p>';
  }

  /* ---- tab 3: weekly summary -------------------------------------------- */

  var lastSummary = null;

  function renderWeekly() {
    var list = rows();
    var summary = APP.weeklySummary(list);
    lastSummary = summary;
    $('weekwindow').textContent = summary.window.start + ' to ' + summary.window.end +
      ' · compared with ' + summary.previous_window.start + ' to ' + summary.previous_window.end +
      ' · computed from ' + list.length + ' stored tickets';
    $('headline').textContent = summary.headline;

    $('findings').innerHTML = summary.findings.map(function (f) {
      var ev = Object.keys(f.evidence || {}).map(function (k) {
        var v = f.evidence[k];
        if (v && typeof v === 'object') v = JSON.stringify(v);
        return esc(k) + ': ' + esc(v);
      }).join(' · ');
      return '<div class="finding ' + esc(f.severity || 'ok') + '">' +
        '<h3>' + esc(f.title) + (f.thin_data ? ' <span class="chip neutral tiny">thin data</span>' : '') + '</h3>' +
        '<p style="margin:0">' + esc(f.detail) + '</p>' +
        '<div class="ev tiny muted mono">' + ev + '</div></div>';
    }).join('');
  }

  function summaryText() {
    if (!lastSummary) return '';
    return 'MedOps weekly summary ' + lastSummary.window.start + ' to ' + lastSummary.window.end + '\n\n' +
      lastSummary.headline + '\n\n' +
      lastSummary.findings.map(function (f) { return '• ' + f.title + '. ' + f.detail; }).join('\n');
  }

  /* ---- store actions ---------------------------------------------------- */

  function resetToSeed() {
    APP.save(JSON.parse(JSON.stringify(SEED)));
    renderAll();
    $('hint').textContent = 'Reset to the ' + SEED.length + ' sample tickets. Your own additions were removed.';
  }

  function downloadCsv() {
    var list = rows();
    var head = ['ticket_id', 'timestamp', 'sender', 'category', 'priority', 'assigned_to', 'status',
      'first_response_at', 'resolved_at', 'response_minutes', 'resolution_minutes', 'summary'];
    var lines = [head.join(',')];
    list.forEach(function (t) {
      lines.push(head.map(function (k) {
        var v = k === 'response_minutes' ? A.responseMinutes(t)
          : (k === 'resolution_minutes' ? A.resolutionMinutes(t)
            : (k === 'status' ? A.statusOf(t) : t[k]));
        v = v === null || v === undefined ? '' : String(v);
        return /[",\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v;
      }).join(','));
    });
    var blob = new Blob([lines.join('\n')], { type: 'text/csv' });
    var a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'medops-tickets.csv';
    a.click();
    URL.revokeObjectURL(a.href);
  }

  function downloadJson() {
    if (!lastSummary) renderWeekly();
    var payload = {
      generated_at: lastSummary.generated_at,
      window: lastSummary.window,
      headline: lastSummary.headline,
      findings: lastSummary.findings,
      analytics: lastSummary.analytics
    };
    var blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
    var a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'medops-weekly-summary-' + lastSummary.window.end + '.json';
    a.click();
    URL.revokeObjectURL(a.href);
  }

  function renderAll() {
    renderLog();
    renderDash();
    renderWeekly();
    $('footmeta').textContent = rows().length + ' tickets in this browser' +
      ' · ' + bundle.semantic.trained_on + ' training documents · ' +
      Object.keys(bundle.semantic.idf).length + ' idf terms';
  }

  /* ---- wiring ----------------------------------------------------------- */

  document.querySelectorAll('.tab').forEach(function (btn) {
    btn.addEventListener('click', function () {
      document.querySelectorAll('.tab').forEach(function (b) {
        b.classList.toggle('on', b === btn);
        b.setAttribute('aria-selected', b === btn ? 'true' : 'false');
      });
      document.querySelectorAll('.panel').forEach(function (p) {
        p.classList.toggle('on', p.id === 'panel-' + btn.dataset.tab);
      });
      if (btn.dataset.tab === 'dash') renderDash();
      if (btn.dataset.tab === 'weekly') renderWeekly();
    });
  });

  $('submit').addEventListener('click', submit);
  $('quick').addEventListener('click', function (e) {
    var b = e.target.closest('[data-sample]');
    if (!b) return;
    $('msg').value = SAMPLES[parseInt(b.dataset.sample, 10)];
    $('msg').focus();
  });
  $('togglejson').addEventListener('click', function () {
    var pre = $('json');
    pre.classList.toggle('hide');
    this.textContent = pre.classList.contains('hide') ? 'show the stored record' : 'hide the stored record';
  });
  $('log').addEventListener('click', function (e) {
    var resolve = e.target.closest('[data-resolve]');
    var reopen = e.target.closest('[data-reopen]');
    try {
      if (resolve) APP.update(resolve.dataset.resolve, 'Resolved');
      if (reopen) APP.update(reopen.dataset.reopen, 'In Progress');
    } catch (err) { $('hint').textContent = err.message; }
    renderAll();
  });
  $('demo').addEventListener('click', resetToSeed);
  $('exportcsv').addEventListener('click', downloadCsv);
  $('clearlog').addEventListener('click', function () {
    var added = rows().length - SEED.length;
    if (added <= 0) { $('hint').textContent = 'Nothing of yours to clear: this is the sample history.'; return; }
    this.textContent = 'Remove ' + added + ' of your tickets?';
    var self = this;
    var yes = document.createElement('button');
    yes.className = 'btn2 tiny';
    yes.textContent = 'Yes, remove';
    yes.onclick = function () {
      resetToSeed();
      self.textContent = 'Clear my tickets';
      yes.remove();
      keep.remove();
    };
    var keep = document.createElement('button');
    keep.className = 'btn2 tiny';
    keep.textContent = 'Keep';
    keep.onclick = function () {
      self.textContent = 'Clear my tickets';
      yes.remove();
      keep.remove();
    };
    this.parentNode.appendChild(yes);
    this.parentNode.appendChild(keep);
  });

  document.querySelectorAll('[data-window]').forEach(function (b) {
    b.addEventListener('click', function () {
      windowMode = b.dataset.window;
      document.querySelectorAll('[data-window]').forEach(function (x) { x.classList.toggle('on', x === b); });
      renderDash();
    });
  });

  $('copy').addEventListener('click', function () {
    var text = summaryText();
    var done = function () { $('copy').textContent = 'Copied'; setTimeout(function () { $('copy').textContent = 'Copy summary'; }, 1600); };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done, function () { fallbackCopy(text, done); });
    } else { fallbackCopy(text, done); }
  });

  function fallbackCopy(text, done) {
    var ta = document.createElement('textarea');
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand('copy'); done(); } catch (e) { /* ignore */ }
    ta.remove();
  }

  $('download').addEventListener('click', downloadJson);

  seedIfEmpty();
  renderQuick();
  renderAll();
  window.__medops = { rows: rows, renderAll: renderAll, seedSize: SEED.length };
})();
