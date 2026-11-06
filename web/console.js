/* MedOps AI console — one page, generator and results together.
 *
 * A ticket you generate here is not a preview. It goes into this browser's store and
 * immediately moves the KPI tiles, the mix charts and the ticket explorer on the same
 * page, because those are all recomputed from the same store.
 *
 * The written executive summary is the one thing that cannot move: it is composed by
 * the Python narrative engine at build time. The page says so rather than pretending.
 *
 * Everything runs locally. The store is localStorage, so it is per browser, not shared.
 * To put tickets into the shared record, export them and run
 * `python -m app.cli import tickets.json`; the next build then includes them everywhere.
 */
(function () {
  'use strict';

  var bundle = __BUNDLE__;
  var baseline = __BASELINE__;
  var STORE_KEY = 'medops.console.tickets.v1';
  var memoryStore = [];       // fallback when localStorage is unavailable
  var storageWorks = true;

  var message = document.getElementById('msg');
  var sender = document.getElementById('sender');
  var out = document.getElementById('out');
  var sessionState = document.getElementById('session-state');

  var examples = [
    { text: 'The ventilator in ICU Bay 3 is alarming and will not start. Patient is on it now.',
      sender: 'Sister Naidoo (ICU)' },
    { text: 'The aircon in Theatre 2 stopped cooling overnight and the room is at 29 degrees. First case is at 8am.',
      sender: 'Dr Pillay (Theatre 2)' },
    { text: 'Please could you send through my payslip for October, the overtime line looks wrong.',
      sender: 'Mr Khumalo (Finance query)' },
    { text: 'Generator did not start during the switch-over test in Block B, and the ward is short two nurses tonight.',
      sender: 'Mr Adams (Block B)' },
    { text: 'The telemetry is down and nobody can see the cardiac monitors on Ward 4.',
      sender: 'Sister Mokoena (Ward 4)' }
  ];

  /* ---------- store ---------- */

  function load() {
    try {
      var raw = window.localStorage.getItem(STORE_KEY);
      return raw ? JSON.parse(raw) : [];
    } catch (error) {
      storageWorks = false;
      return memoryStore;
    }
  }

  function save(tickets) {
    memoryStore = tickets;
    try {
      window.localStorage.setItem(STORE_KEY, JSON.stringify(tickets));
    } catch (error) {
      storageWorks = false;
    }
  }

  function nextId(tickets) {
    return 'MED-WEB-' + String(tickets.length + 1).padStart(2, '0');
  }

  /* ---------- small dom helpers ---------- */

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }

  function clear(node) {
    while (node.firstChild) node.removeChild(node.firstChild);
  }

  function setKpi(id, value, sub) {
    var tile = document.getElementById(id);
    if (!tile) return;
    var valueNode = tile.querySelector('.tvalue');
    var subNode = tile.querySelector('.tsub');
    if (valueNode && value !== undefined) valueNode.textContent = value;
    if (subNode && sub !== undefined) subNode.textContent = sub;
  }

  function priorityClass(priority) {
    return priority === 'High' ? 'p-high' : priority === 'Medium' ? 'p-mid' : 'p-low';
  }

  function percent(part, whole) {
    if (!whole) return '—';
    return Math.round((part / whole) * 100) + '%';
  }

  /* ---------- charts: the same geometry as scripts/build_pages.py hbars() ---------- */

  function hbars(container, pairs) {
    if (!container) return;
    clear(container);
    var width = baseline.bar.width;
    var rowh = baseline.bar.rowh;
    var top = Math.max.apply(null, pairs.map(function (p) { return p[1]; }).concat([1]));
    var height = rowh * pairs.length;
    var svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('viewBox', '0 0 ' + width + ' ' + height);
    svg.setAttribute('width', '100%');
    svg.setAttribute('height', height);
    svg.setAttribute('role', 'img');

    pairs.forEach(function (pair, index) {
      var label = pair[0];
      var value = pair[1];
      var w = (value / top) * (width - 190);
      var y = index * rowh;

      var text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      text.setAttribute('x', 0); text.setAttribute('y', y + 15);
      text.setAttribute('fill', baseline.bar.text);
      text.setAttribute('font-size', 13);
      text.textContent = label;
      svg.appendChild(text);

      var rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
      rect.setAttribute('x', 150); rect.setAttribute('y', y + 4);
      rect.setAttribute('width', w.toFixed(1)); rect.setAttribute('height', 18);
      rect.setAttribute('rx', 4); rect.setAttribute('fill', baseline.bar.colour);
      svg.appendChild(rect);

      var count = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      count.setAttribute('x', (150 + w + 8).toFixed(1));
      count.setAttribute('y', y + 18);
      count.setAttribute('fill', baseline.bar.muted);
      count.setAttribute('font-size', 12);
      count.textContent = value;
      svg.appendChild(count);
    });
    container.appendChild(svg);
  }

  /* ---------- dashboard recompute ---------- */

  function sessionWithinWindow(tickets) {
    return tickets.filter(function (ticket) {
      var day = (ticket.created_at || '').slice(0, 10);
      return day >= baseline.window.start && day <= baseline.window.end;
    });
  }

  function renderDashboard(tickets) {
    var inWindow = sessionWithinWindow(tickets);
    var totals = baseline.all_time;
    var high = tickets.filter(function (t) { return t.priority === 'High'; }).length;

    setKpi('kpi-window', totals && baseline.window_total + inWindow.length,
      baseline.window.start + ' to ' + baseline.window.end +
      (inWindow.length ? ' · includes ' + inWindow.length + ' you added' : ''));

    setKpi('kpi-high', percent(totals.high + high, totals.total + tickets.length),
      'all time · ' + (totals.high + high) + ' of ' + (totals.total + tickets.length));

    setKpi('kpi-open', totals.open + tickets.length,
      'all time · ' + totals.in_progress + ' in progress · ' + totals.resolved + ' resolved' +
      (tickets.length ? ' · ' + tickets.length + ' new' : ''));

    if (tickets.length) {
      setKpi('kpi-median', undefined,
        'all time · ' + baseline.answered + ' answered of ' + (totals.total + tickets.length) +
        ' · your ' + tickets.length + ' unanswered ticket(s) are not in this figure');
    } else {
      setKpi('kpi-median', undefined,
        'all time · ' + baseline.answered + ' answered of ' + totals.total);
    }

    var categories = {};
    Object.keys(baseline.categories).forEach(function (key) { categories[key] = baseline.categories[key]; });
    var priorities = {};
    Object.keys(baseline.priorities).forEach(function (key) { priorities[key] = baseline.priorities[key]; });
    tickets.forEach(function (ticket) {
      categories[ticket.category] = (categories[ticket.category] || 0) + 1;
      priorities[ticket.priority] = (priorities[ticket.priority] || 0) + 1;
    });

    hbars(document.getElementById('chart-cat'), Object.keys(categories).map(function (key) {
      return [key, categories[key]];
    }));
    hbars(document.getElementById('chart-pri'), Object.keys(priorities).map(function (key) {
      return [key, priorities[key]];
    }));

    renderSessionState(tickets);
  }

  /* ---------- explorer ---------- */

  function explorerRow(ticket) {
    var row = el('tr');
    row.setAttribute('data-c', ticket.category);
    row.setAttribute('data-p', ticket.priority);
    row.setAttribute('data-s', ticket.status);
    row.setAttribute('data-session', '1');
    row.setAttribute('data-t', (ticket.message + ' ' + ticket.assigned_to + ' ' + ticket.id).toLowerCase());

    row.appendChild(el('td', 'mono', ticket.id));
    var messageCell = el('td', 'msg', (ticket.message || '').slice(0, 96));
    var badge = el('span', 'chip new', 'new');
    messageCell.appendChild(badge);
    row.appendChild(messageCell);
    var categoryCell = el('td');
    categoryCell.appendChild(el('span', 'chip', ticket.category));
    row.appendChild(categoryCell);
    var priorityCell = el('td');
    priorityCell.appendChild(el('span', 'chip ' + priorityClass(ticket.priority), ticket.priority));
    row.appendChild(priorityCell);
    row.appendChild(el('td', null, ticket.assigned_to));
    var statusCell = el('td');
    statusCell.appendChild(el('span', 'dot s-Open', ticket.status));
    row.appendChild(statusCell);
    row.appendChild(el('td', 'num', '—'));
    return row;
  }

  function syncExplorer(tickets) {
    var body = document.getElementById('rows');
    if (!body) return;
    var existing = body.querySelectorAll('tr[data-session="1"]');
    for (var i = 0; i < existing.length; i++) existing[i].remove();
    // newest first, matching the table's ordering
    tickets.slice().reverse().forEach(function (ticket) {
      body.insertBefore(explorerRow(ticket), body.firstChild);
    });
    if (window.medopsApplyFilters) window.medopsApplyFilters();
  }

  /* ---------- session state strip ---------- */

  function renderSessionState(tickets) {
    if (!sessionState) return;
    clear(sessionState);
    if (!tickets.length) {
      sessionState.appendChild(el('span', 'small muted',
        'No tickets added yet. Generate one and it appears in the tiles, the charts and the table below.'));
      return;
    }
    var open = tickets.filter(function (t) { return t.status === 'Open'; }).length;
    sessionState.appendChild(el('span', 'small',
      tickets.length + ' ticket(s) added in this browser · ' + open + ' Open · ' +
      (storageWorks ? 'stored in this browser only' : 'not stored (storage blocked)')));
    sessionState.appendChild(clearControl(tickets));
    var csv = el('button', 'ghost small-btn', 'Download CSV');
    csv.addEventListener('click', function () { download('medops-my-tickets.csv', toCsv(tickets), 'text/csv'); });
    sessionState.appendChild(csv);
    var json = el('button', 'ghost small-btn', 'Export for import');
    json.addEventListener('click', function () { download('medops-my-tickets.json', toExport(tickets), 'application/json'); });
    sessionState.appendChild(json);
    var note = el('p', 'small muted');
    note.textContent = 'To add them to the shared record: run python -m app.cli import ' +
      'medops-my-tickets.json, then rebuild the page. The written summary below is ' +
      'composed at build time, so it keeps describing the committed store until then.';
    sessionState.appendChild(note);
  }

  /* Two-step clear. A native confirm() blocks the page and cannot be styled, and this
   * is destructive, so it gets an explicit second click instead. */
  function clearControl(tickets) {
    var wrap = el('span', 'confirm-wrap');
    var button = el('button', 'ghost small-btn', 'Clear my tickets');
    button.addEventListener('click', function () {
      clear(wrap);
      wrap.appendChild(el('span', 'small', 'Remove all ' + tickets.length + '?'));
      var yes = el('button', 'small-btn danger', 'Yes, remove');
      yes.addEventListener('click', function () { save([]); paint([]); clear(out); });
      var no = el('button', 'small-btn', 'Keep');
      no.addEventListener('click', function () { renderSessionState(load()); });
      wrap.appendChild(yes);
      wrap.appendChild(no);
    });
    wrap.appendChild(button);
    return wrap;
  }

  /* ---------- export ---------- */

  function download(name, text, type) {
    var blob = new Blob([text], { type: type + ';charset=utf-8' });
    var url = URL.createObjectURL(blob);
    var link = document.createElement('a');
    link.href = url;
    link.download = name;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  }

  function toCsv(tickets) { return MedOpsExport.toCsv(tickets); }
  function toExport(tickets) { return MedOpsExport.toExport(tickets); }

  /* ---------- the generated ticket ---------- */

  function renderTicket(ticket, index, total) {
    clear(out);
    var head = el('div', 'ticket-head');
    head.appendChild(el('span', 'mono small muted', ticket.id));
    head.appendChild(el('span', 'small muted', 'added to this browser · ticket ' + index + ' of ' + total));
    out.appendChild(head);

    var badges = el('div', 'badges');
    badges.appendChild(el('span', 'chip accent', ticket.category));
    badges.appendChild(el('span', 'chip ' + priorityClass(ticket.priority), ticket.priority + ' priority'));
    out.appendChild(badges);

    var routed = el('p', 'routed');
    routed.appendChild(el('span', 'small muted', 'Routed to '));
    routed.appendChild(el('b', null, ticket.assigned_to));
    out.appendChild(routed);

    var scores = el('div', 'scores');
    var totalScore = Object.keys(ticket.scores).reduce(function (sum, key) { return sum + ticket.scores[key]; }, 0);
    scores.appendChild(el('p', 'small muted', 'Category scores' + (totalScore === 0
      ? ' (no keyword matched, so the operations catch-all applies)'
      : ' — confidence ' + Math.round(ticket.confidence * 100) + '%')));
    Object.keys(ticket.scores).forEach(function (category) {
      var share = totalScore === 0 ? 0 : Math.round((ticket.scores[category] / totalScore) * 100);
      var row = el('div', 'score-row');
      row.appendChild(el('span', 'score-label', category));
      var track = el('span', 'score-track');
      var fill = el('span', 'score-fill' + (category === ticket.category ? '' : ' dim'));
      fill.style.width = share + '%';
      track.appendChild(fill);
      row.appendChild(track);
      row.appendChild(el('span', 'score-value mono', ticket.scores[category]));
      scores.appendChild(row);
    });
    out.appendChild(scores);

    var why = el('div', 'why');
    why.appendChild(el('p', 'small muted', 'Priority score ' + ticket.score + ' (5+ is High, 2-4 is Medium)'));
    if (!ticket.signals.length) {
      why.appendChild(el('p', 'small', 'No priority signal fired, so it sits at Low.'));
    } else {
      var list = el('ul', 'signals');
      ticket.signals.forEach(function (signal) {
        var item = el('li');
        item.appendChild(el('span', 'chip ' + (signal.points > 0 ? 'p-mid' : 'p-low'),
          (signal.points > 0 ? '+' : '') + signal.points));
        item.appendChild(el('span', 'signal-label', signal.label));
        item.appendChild(el('span', 'small muted', ' (' + signal.detail + ')'));
        list.appendChild(item);
      });
      why.appendChild(list);
    }
    out.appendChild(why);

    var block = el('blockquote', 'summary-out');
    block.appendChild(el('span', 'small muted block', 'One-sentence summary'));
    block.appendChild(el('p', null, ticket.summary));
    out.appendChild(block);

    out.appendChild(el('p', 'small muted',
      'Sender read as: ' + ticket.sender + '. The patient-data screen and the drafted ' +
      'reply need the Python console; this page runs the classification core only.'));
  }

  function paint(tickets) {
    renderDashboard(tickets);
    syncExplorer(tickets);
  }

  function generate(persist) {
    var text = (message.value || '').trim();
    if (!text) {
      clear(out);
      out.appendChild(el('p', 'small', 'Type a message first.'));
      return;
    }
    var result = MedOpsEngine.generate(text, bundle, { sender: (sender.value || '').trim() });
    var tickets = load();
    var ticket = {
      id: nextId(tickets),
      created_at: new Date().toISOString().slice(0, 19) + 'Z',
      message: result.message,
      sender: result.sender,
      category: result.category,
      priority: result.priority,
      assigned_to: result.assigned_to,
      summary: result.summary,
      status: 'Open',
      confidence: result.confidence,
      scores: result.scores,
      score: result.score,
      signals: result.signals
    };
    if (persist !== false) {
      tickets.push(ticket);
      save(tickets);
    }
    renderTicket(ticket, (persist === false ? tickets.length : tickets.length), tickets.length);
    paint(tickets);
  }

  /* ---------- wiring ---------- */

  document.getElementById('go').addEventListener('click', function () { generate(true); });
  document.getElementById('another').addEventListener('click', function () {
    var next = examples[Math.floor(Math.random() * examples.length)];
    message.value = next.text;
    sender.value = next.sender;
  });
  message.addEventListener('keydown', function (event) {
    if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') generate(true);
  });

  var stored = load();
  if (stored.length) {
    var last = stored[stored.length - 1];
    message.value = last.message;
    sender.value = last.sender;
    if (last.scores) renderTicket(last, stored.length, stored.length);
  }
  paint(stored);
})();
