/* MedOps AI — browser engine.
 *
 * A faithful port of the deterministic core in app/: parser.py, classifier.py,
 * prioritizer.py, assigner.py and summarizer.py. All keyword tables, the routing
 * table and the sender regexes are injected from the Python modules at build time
 * (see scripts/build_pages.py), so the only duplicated thing here is the handful of
 * lines of control flow, not the knowledge.
 *
 * It exists because the published page is static: GitHub Pages cannot run Python, and
 * a form that only looks like a form would be a lie. Everything below runs locally in
 * the reader's browser. Nothing is sent anywhere and nothing is stored.
 *
 * Drift is checked, not assumed: scripts/check_engine_parity.mjs replays several
 * hundred real messages through both this file and the Python engine and fails on any
 * difference. tests/test_web_engine_parity.py runs it inside pytest.
 */
var MedOpsEngine = (function () {
  'use strict';

  function countAll(text, needle) {
    // Python's str.count counts non-overlapping occurrences; split does the same.
    if (!needle) return 0;
    return text.split(needle).length - 1;
  }

  /* Python's \w is Unicode-aware (é, ṋ, combining marks); JavaScript's is ASCII only.
   * Translating the class and adding the u flag keeps sender names across the two
   * languages in agreement, which the parity check would otherwise flag. */
  function compile(pattern, flags) {
    // \w always appears inside a character class in these patterns, so the
    // replacement is the class body, not a nested class.
    var translated = pattern.replace(/\\w/g, '\\p{L}\\p{N}\\p{M}_');
    return new RegExp(translated, flags + 'u');
  }

  function dequote(text) {
    if (text.startsWith('"')) text = text.slice(1);
    if (text.endsWith('"')) text = text.slice(0, -1);
    text = text.replace(/\.\" /g, '. ');
    return text.trim();
  }

  function parseSender(raw, bundle, override) {
    var text = raw.trim();
    if (override) return { body: dequote(text), sender: override };

    var fromRe = compile(bundle.parser.from, bundle.parser.from_flags);
    var from = fromRe.exec(text);
    if (from) {
      var body = dequote(text.replace(from[0], '').trim());
      return { body: body, sender: from[1].trim() };
    }

    var signedRe = compile(bundle.parser.signed, bundle.parser.signed_flags);
    var signed = signedRe.exec(text);
    if (signed) {
      var name = signed[1].trim();
      var dept = signed[2].trim();
      var signedAll = compile(bundle.parser.signed, bundle.parser.signed_flags + 'g');
      return { body: dequote(text.replace(signedAll, '').trim()), sender: name + ' (' + dept + ')' };
    }
    return { body: dequote(text), sender: 'Unspecified hospital staff' };
  }

  function classify(message, bundle) {
    var text = message.toLowerCase();
    var scores = {};
    var total = 0;
    Object.keys(bundle.category_keywords).forEach(function (category) {
      var score = 0;
      var keywords = bundle.category_keywords[category];
      Object.keys(keywords).forEach(function (keyword) {
        if (text.indexOf(keyword) !== -1) score += keywords[keyword] * countAll(text, keyword);
      });
      scores[category] = score;
      total += score;
    });
    if (total === 0) return { category: bundle.default_category, confidence: 0, scores: scores };
    var best = null;
    Object.keys(scores).forEach(function (category) {
      if (best === null || scores[category] > scores[best]) best = category;
    });
    return { category: best, confidence: Math.round((scores[best] / total) * 1000) / 1000, scores: scores };
  }

  function prioritize(message, sender, bundle) {
    var text = (message + ' ' + (sender || '')).toLowerCase();
    var rules = bundle.priority;
    var score = 0;
    var signals = [];

    function hit(list) {
      for (var i = 0; i < list.length; i++) if (text.indexOf(list[i]) !== -1) return list[i];
      return null;
    }

    var clinical = hit(rules.clinical_context);
    if (clinical) { score += 3; signals.push({ label: 'clinical area named', detail: clinical, points: 3 }); }

    var equipment = hit(rules.clinical_equipment);
    if (equipment) { score += 3; signals.push({ label: 'clinical equipment named', detail: equipment, points: 3 }); }

    var safety = hit(rules.safety);
    if (safety) { score += 4; signals.push({ label: 'safety hazard', detail: safety, points: 4 }); }

    var urgent = hit(rules.urgent);
    if (urgent) { score += 2; signals.push({ label: 'failure or urgency language', detail: urgent, points: 2 }); }

    if (hit(rules.staffing_critical) && hit(rules.clinical_context)) {
      score += 3;
      signals.push({ label: 'understaffing in a clinical area', detail: 'treated as a safety event', points: 3 });
    }

    var routine = hit(rules.routine);
    if (routine) { score -= 2; signals.push({ label: 'routine administrative wording', detail: routine, points: -2 }); }

    if (text.indexOf('high') !== -1 || text.indexOf('emergency') !== -1) {
      score += 1;
      signals.push({ label: 'escalation word in the message', detail: 'high / emergency', points: 1 });
    }

    var priority = score >= rules.high_threshold ? 'High'
                 : score >= rules.medium_threshold ? 'Medium'
                 : 'Low';
    return { priority: priority, score: score, signals: signals };
  }

  function route(category, priority, bundle) {
    return bundle.assign[category][priority];
  }

  function summarize(message, sender, category, priority, bundle) {
    var core = message.trim().replace(/\.+$/, '').replace(/\s+/g, ' ');
    var words = core.split(' ');
    if (words.length > bundle.summary.max_words) {
      core = words.slice(0, bundle.summary.max_words).join(' ') + '...';
    }
    var dept = sender.indexOf('(') !== -1
      ? sender.split('(').pop().replace(/\)+$/, '')
      : 'hospital staff';
    return core + '. Reported by ' + dept + '; classified as ' + category + ' with ' + priority + ' priority.';
  }

  /* One message in, one ticket out — the same order pipeline.process_ticket uses,
   * minus persistence, which a static page cannot do honestly. */
  function generate(raw, bundle, options) {
    options = options || {};
    var parsed = parseSender(raw, bundle, options.sender || null);
    var classification = classify(parsed.body, bundle);
    var triage = prioritize(parsed.body, parsed.sender, bundle);
    return {
      message: parsed.body,
      sender: parsed.sender,
      category: classification.category,
      confidence: classification.confidence,
      scores: classification.scores,
      priority: triage.priority,
      score: triage.score,
      signals: triage.signals,
      assigned_to: route(classification.category, triage.priority, bundle),
      summary: summarize(parsed.body, parsed.sender, classification.category, triage.priority, bundle)
    };
  }

  return { generate: generate, classify: classify, prioritize: prioritize, parseSender: parseSender };
})();

if (typeof module !== 'undefined' && module.exports) module.exports = MedOpsEngine;
