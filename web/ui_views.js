/* MedOps AI: the three workflow views the platform was missing.
 *
 * 1. Tone control on a drafted reply (Week 2). Re-drafts the SAME ticket in the
 *    chosen register; facts (id, team, window) do not move.
 * 2. Predictive workload (Week 5): the 7-day projection AND the method comparison,
 *    so the page shows the backtest error next to the number instead of alone.
 * 3. Governance (Week 6): matched-pair bias audit, decision log, transparency note.
 *
 * Everything here runs in the browser on the shipped bundle. No network calls, no
 * invented numbers: if a calculation cannot be made from the stored tickets, the
 * view says so rather than filling the space.
 */
(function (root) {
  var $ = function (id) { return document.getElementById(id); };
  var esc = function (s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  };
  var APP = root.MedOpsApp;
  var G = root.MedOpsGovernance;

  /* the parity module is authored alongside; accept either naming convention */
  function pick() {
    for (var i = 0; i < arguments.length; i++) {
      if (G && typeof G[arguments[i]] === 'function') return G[arguments[i]];
    }
    return null;
  }
  var fnForecast = function () { return pick('forecastVolume', 'forecast_volume'); };
  var fnCompare = function () { return pick('compareMethods', 'compare_methods'); };
  var fnAudit = function () { return pick('runBiasAudit', 'run_audit'); };
  var fnPrioritize = function () { return pick('prioritize'); };
  var fnDecision = function () { return pick('buildDecisionRecord', 'build_record'); };
  var fnTransparency = function () { return pick('transparencyNote', 'transparency_note'); };

  var TONES = [
    { id: 'formal', label: 'Formal' },
    { id: 'friendly', label: 'Friendly' },
    { id: 'urgent', label: 'Urgent' }
  ];

  /* ---------- 1. tone control ---------- */
  function enhanceReply(ticket) {
    var box = $('replybox');
    if (!box || !ticket || !ticket.ticket_id) return;
    var current = (ticket.ai_response && ticket.ai_response.tone) || '';
    var bar = document.createElement('div');
    bar.className = 'row';
    bar.style.marginTop = '10px';
    bar.innerHTML = '<span class="small muted">Tone</span>';
    var seg = document.createElement('div');
    seg.className = 'seg';
    seg.setAttribute('role', 'group');
    seg.setAttribute('aria-label', 'Reply tone');
    TONES.forEach(function (tone) {
      var b = document.createElement('button');
      b.type = 'button';
      b.textContent = tone.label;
      b.setAttribute('aria-pressed', String(current === tone.id));
      if (current === tone.id) b.className = 'on';
      b.addEventListener('click', function () { applyTone(ticket.ticket_id, tone.id); });
      seg.appendChild(b);
    });
    var note = document.createElement('span');
    note.className = 'tiny faint';
    note.textContent = 'Tone changes courtesy only. Ticket, team and response window stay the same.';
    bar.appendChild(seg);
    bar.appendChild(note);
    box.appendChild(bar);
  }

  function applyTone(ticketId, tone) {
    try {
      var rows = APP.load();
      var t = rows.filter(function (r) { return r.ticket_id === ticketId; })[0];
      if (!t) return;
      t.ai_response = APP.draftReply(t, tone);
      APP.save(rows);
      // renderAll() skips the ticket panel, so the reply itself has to be re-rendered
      // explicitly or the new tone is saved but never seen.
      if (root.__medops && root.__medops.renderTicket) root.__medops.renderTicket(t);
      if (root.__medops && root.__medops.renderAll) root.__medops.renderAll();
    } catch (err) {
      var box = $('replybox');
      if (box) box.insertAdjacentHTML('afterbegin',
        '<div class="alert err">Could not re-draft in that tone: ' + esc(err.message) + '</div>');
    }
  }

  /* ---------- shared: daily counts from the stored tickets ---------- */
  function byDay(rows) {
    var map = {};
    rows.forEach(function (r) {
      if (!r || !r.timestamp) return;
      var d = String(r.timestamp).slice(0, 10);
      map[d] = (map[d] || 0) + 1;
    });
    return Object.keys(map).sort().map(function (d) { return { date: d, count: map[d] }; });
  }

  /* ---------- 2. predictive workload ---------- */
  function renderForecast() {
    var host = $('fcBody');
    if (!host) return;
    var rows = APP.load();
    var series = byDay(rows);
    var fc = fnForecast();
    var cmp = fnCompare();

    if (!fc) {
      host.innerHTML = '<div class="alert info">The browser engine for forecasting did not load, so this view is empty rather than wrong.</div>';
      return;
    }
    if (series.length < 3) {
      host.innerHTML = '<div class="empty"><strong>Not enough history to project</strong>' +
        'A forecast needs several days of tickets. Log requests, or reset to the sample history.</div>';
      return;
    }

    var out = fc(series, 7);
    var cmpOut = cmp ? cmp(series) : null;

    var max = 1;
    out.forecast.concat(series.slice(-14)).forEach(function (p) { max = Math.max(max, p.count || p.predicted || 0); });

    var bars = out.forecast.map(function (p) {
      var h = Math.round((p.predicted / max) * 100);
      return '<div style="display:flex;flex-direction:column;justify-content:flex-end;align-items:center;flex:1;gap:6px">' +
        '<span class="tiny num faint">' + p.predicted + '</span>' +
        '<div title="' + esc(p.date) + ': ' + p.predicted + ' tickets"' +
        ' style="width:100%;max-width:38px;height:' + Math.max(4, h) + 'px;background:var(--ink);border-radius:4px 4px 2px 2px"></div>' +
        '<span class="tiny faint">' + esc(String(p.date).slice(5)) + '</span></div>';
    }).join('');

    var errLine = out.backtest_mae === null || out.backtest_mae === undefined
      ? '<span class="chip warn">no error margin quotable yet</span>'
      : '<span class="chip neutral">backtest error &plusmn;' + out.backtest_mae + ' tickets/day</span>';

    host.innerHTML =
      '<div class="grid" style="margin-bottom:16px">' +
        '<div class="kpi"><div class="label">Projected next 7 days</div>' +
          '<div class="value num">' + out.predicted_total + '</div>' +
          '<div class="note">' + esc(out.method) + '</div></div>' +
        '<div class="kpi"><div class="label">History used</div>' +
          '<div class="value num">' + out.history_days + ' days</div>' +
          '<div class="note">' + (out.reliable ? 'enough to fit a trend' : 'short history: average only') + '</div></div>' +
        '<div class="kpi"><div class="label">Confidence in the number</div>' +
          '<div class="value" style="font-size:17px;line-height:1.4">' + errLine + '</div>' +
          '<div class="note">Always shown with the projection, never after it.</div></div>' +
      '</div>' +
      '<div class="card"><div class="card-head"><h3>Projected workload, next 7 days</h3>' +
        '<span class="tiny faint">planning aid, not a prediction</span></div>' +
        '<div style="display:flex;gap:6px;align-items:flex-end;height:140px">' + bars + '</div></div>' +
      (cmpOut ? '<div class="card"><h3>Which method should you trust?</h3>' +
        '<p class="small muted" style="margin-top:4px">Three methods scored the same way, one day at a time, ' +
        'using only what was known the day before.</p>' +
        '<table><thead><tr><th>Method</th><th class="num">Average miss</th></tr></thead><tbody>' +
        (cmpOut.methods || []).map(function (m) {
          return '<tr><td>' + esc(m.method) + (m.method === cmpOut.best ? ' <span class="chip neutral">best</span>' : '') +
            '</td><td class="num">' + m.mae + '</td></tr>';
        }).join('') + '</tbody></table>' +
        '<div class="alert ' + (cmpOut.distinguishable_from_luck ? 'info' : 'info') + '" style="margin-top:12px">' +
          esc(cmpOut.verdict) + '</div>' +
        (cmpOut.interval_95 ? '<p class="tiny faint" style="margin-top:8px">Advantage ' +
          cmpOut.advantage_tickets_per_day + ' tickets/day, 95% interval [' + cmpOut.interval_95[0] + ', ' +
          cmpOut.interval_95[1] + '] over ' + cmpOut.test_days + ' test days.</p>' : '') +
        '</div>' : '');
  }

  /* ---------- 3. governance ---------- */
  function renderGovernance() {
    var host = $('govBody');
    if (!host) return;
    var audit = fnAudit(), prio = fnPrioritize(), decision = fnDecision(), transp = fnTransparency();
    var html = '';

    if (audit && prio) {
      var a = audit(function (text) { return { priority: prio(text, '') }; });
      var rows = (a.rows || []).map(function (r) {
        var ok = r.consistent;
        return '<tr><td>' + esc(r.need) + '</td>' +
          '<td>' + esc(r.variant_a) + ' <span class="chip ' + (r.priority_a === 'High' ? 'hi' : r.priority_a === 'Medium' ? 'med' : 'low') + '">' + esc(r.priority_a) + '</span></td>' +
          '<td>' + esc(r.variant_b) + ' <span class="chip ' + (r.priority_b === 'High' ? 'hi' : r.priority_b === 'Medium' ? 'med' : 'low') + '">' + esc(r.priority_b) + '</span></td>' +
          '<td>' + (ok ? '<span class="chip low">consistent</span>' : '<span class="chip hi">differs</span>') + '</td></tr>';
      }).join('');

      html += '<div class="card"><div class="card-head"><h3>Bias audit: same need, different wording</h3>' +
        '<span class="chip ' + (a.inconsistent ? 'hi' : 'low') + '">' + a.inconsistent + ' of ' + a.pairs_tested + ' differ</span></div>' +
        '<p class="small muted" style="margin-top:2px">Each pair describes the same underlying problem. If the ' +
        'system is fair, both get the same priority.</p>' +
        '<div class="alert ' + (a.inconsistent ? 'err' : 'info') + '" style="margin:12px 0">' + esc(a.verdict) + '</div>' +
        '<table><thead><tr><th>Need</th><th>Wording</th><th>Reference</th><th></th></tr></thead><tbody>' + rows + '</tbody></table>' +
        '<p class="tiny faint" style="margin-top:10px">' + esc(a.limits || '') + '</p>' +
        '<p class="tiny faint">Detected and surfaced, not corrected: a flagged ticket asks a person to confirm the priority.</p>' +
        '</div>';
    } else {
      html += '<div class="card"><div class="alert info">The bias audit module did not load in this page, ' +
        'so no audit is shown rather than a stale one.</div></div>';
    }

    // Decision log: only local tickets that still carry their raw message.
    var rows2 = APP.load().filter(function (t) { return t && t.raw_message; });
    if (decision && transp) {
      var records = rows2.map(function (t) { return decision(t.raw_message, t); });
      var note = transp(records);
      var flagged = records.filter(function (r) { return r.needs_bias_review; });
      html += '<div class="card"><div class="card-head"><h3>Decision log &amp; transparency note</h3>' +
        '<span class="chip neutral">' + records.length + ' logged in this browser</span></div>' +
        '<p class="small muted" style="margin-top:2px">Written when a ticket is logged. Stores which signals fired, ' +
        'never the message text, so the log cannot become a new place where patient details are kept.</p>' +
        '<div class="alert ' + (flagged.length ? 'err' : 'info') + '" style="margin:12px 0">' + esc(note.note || '') + '</div>' +
        (records.length ? '<table><thead><tr><th>Ticket</th><th>Priority</th><th>Signals</th><th>Language</th><th></th></tr></thead><tbody>' +
          records.slice(-12).reverse().map(function (r) {
            return '<tr><td class="mono">' + esc(r.ticket_id) + '</td>' +
              '<td><span class="chip ' + (r.priority === 'High' ? 'hi' : r.priority === 'Medium' ? 'med' : 'low') + '">' + esc(r.priority) + '</span></td>' +
              '<td class="tiny">' + esc((r.signals_fired || []).join(', ') || 'none') + '</td>' +
              '<td class="tiny">' + esc(r.language_hint) + '</td>' +
              '<td>' + (r.needs_bias_review ? '<span class="chip warn">review</span>' : '') + '</td></tr>';
          }).join('') + '</tbody></table>'
          : '<div class="empty"><strong>No decisions logged yet</strong>Log a request and its decision appears here.</div>') +
        '<p class="tiny faint" style="margin-top:10px">' + esc(note.limits || '') + '</p></div>';
    }
    host.innerHTML = html;
  }

  function renderAll() { renderForecast(); renderGovernance(); }


  /* ---------- 4. role views ----------
     This HIDES views; it does not enforce access. Any visitor can change the role,
     and there is no server to refuse them, so the note on screen says exactly that.
     Real scopes belong in the API once it is hosted (#17). */
  var ROLE_KEY = 'medops.role.v1';
  var ROLES = {
    staff: {
      tabs: ['log'],
      hideQueueCount: true,
      hideLogTable: true,
      note: '<b>Staff view.</b> You can submit a request and see the one you submitted. ' +
            'Not enforced: this page has no sign-in, so it hides the queue rather than locking it.'
    },
    operations: {
      tabs: ['log', 'dash', 'forecast', 'weekly'],
      hideQueueCount: false,
      hideLogTable: false,
      note: '<b>Operations view.</b> Triage queue, workload and reporting for the whole hospital.'
    },
    governance: {
      tabs: ['governance'],
      hideQueueCount: true,
      hideLogTable: true,
      note: '<b>Governance view, read-only.</b> Bias audit, decision log and transparency note. ' +
            'No ability to change a ticket.'
    }
  };

  function currentRole() {
    try { return root.localStorage.getItem(ROLE_KEY) || 'operations'; } catch (e) { return 'operations'; }
  }

  function applyRole(role) {
    var cfg = ROLES[role] ? role : 'operations';
    var spec = ROLES[cfg];

    document.querySelectorAll('[data-tab]').forEach(function (btn) {
      var tab = btn.getAttribute('data-tab');
      var allowed = spec.tabs.indexOf(tab) !== -1;
      btn.classList.toggle('hide', !allowed);
      btn.setAttribute('aria-hidden', allowed ? 'false' : 'true');
      btn.tabIndex = allowed ? 0 : -1;
    });
    document.querySelectorAll('.panel').forEach(function (p) {
      var tab = p.id.replace('panel-', '');
      if (spec.tabs.indexOf(tab) === -1) p.classList.remove('on');
    });

    // Keep the user somewhere they are allowed to be.
    var active = document.querySelector('.tab.on');
    if (!active || active.classList.contains('hide')) {
      var first = document.querySelector('[data-tab="' + spec.tabs[0] + '"]');
      if (first) first.click();
    }

    var count = $('queueCount');
    if (count) count.classList.toggle('hide', spec.hideQueueCount);

    var logCard = $('log') && $('log').closest('.card');
    if (logCard) logCard.classList.toggle('hide', spec.hideLogTable);

    var note = $('roleNote');
    if (note) note.innerHTML = spec.note;

    var sel = $('roleSel');
    if (sel && sel.value !== cfg) sel.value = cfg;

    try { root.localStorage.setItem(ROLE_KEY, cfg); } catch (e) { /* private mode */ }
    if (cfg === 'governance') renderGovernance();
    if (cfg === 'operations' && $('panel-forecast') && $('panel-forecast').classList.contains('on')) renderForecast();
  }

  function queueCount() {
    var el = $('queueCount');
    if (!el) return;
    var open = APP.load().filter(function (t) { return (t.status || 'Open') !== 'Resolved'; }).length;
    el.textContent = String(open);
  }

  function bootstrap() {
    renderAll();
    queueCount();
    var sel = $('roleSel');
    if (sel) {
      sel.addEventListener('change', function () { applyRole(sel.value); });
      sel.value = currentRole();
    }
    applyRole(currentRole());
    // Views only compute when shown: a tablet opening the triage queue should not pay
    // for a bootstrap over every ticket.
    document.addEventListener('click', function (e) {
      var tab = e.target.closest && e.target.closest('[data-tab]');
      if (!tab) return;
      var which = tab.getAttribute('data-tab');
      setTimeout(function () {
        if (which === 'forecast') renderForecast();
        if (which === 'governance') renderGovernance();
        queueCount();
      }, 0);
    });
  }

  root.MedOpsViews = { applyRole: applyRole, enhanceReply: enhanceReply, renderForecast: renderForecast, renderGovernance: renderGovernance, renderAll: renderAll, queueCount: queueCount };
  if (typeof document !== 'undefined') {
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', bootstrap);
    else bootstrap();
  }
})(typeof window !== 'undefined' ? window : globalThis);
