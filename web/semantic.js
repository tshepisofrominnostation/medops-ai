/* Semantic layer, in the browser.
 *
 * The IDF weights, the per-category centroids and the PHI rules are exported from the
 * Python service by scripts/build_app_bundle.py — they are not re-typed here. What this
 * file adds is only the arithmetic Python does at request time (tokenise, project,
 * cosine) plus the reading of the result. scripts/check_app_parity.mjs replays messages
 * through both implementations and fails on any disagreement.
 */
(function (root) {
  'use strict';

  var B = null;
  var STOP = ('a an the and or but if of to in on at for from by with as is are was were be been ' +
    'being it its this that these those i me my we our you your he she they them their there here ' +
    'has have had do does did not no so than too very can could should would will just also into ' +
    'out up down over under again then once please kindly').split(' ');

  function init(bundle) {
    B = bundle;
    return API;
  }

  function tokenize(text) {
    var words = (String(text || '').toLowerCase().match(/[a-z][a-z\-']+/g) || [])
      .filter(function (w) { return STOP.indexOf(w) === -1; });
    var out = [];
    for (var i = 0; i < words.length; i++) {
      var w = words[i];
      var stem = w.length > 4 ? w.replace(/(ing|ed|es|s|ly)$/, '') : w;
      out.push(stem);
      if (stem.length >= 6) {
        for (var j = 0; j + 3 <= stem.length; j++) out.push('#' + stem.slice(j, j + 3));
      }
    }
    return out;
  }

  function tf(tokens) {
    var counts = {};
    for (var i = 0; i < tokens.length; i++) counts[tokens[i]] = (counts[tokens[i]] || 0) + 1;
    var out = {};
    for (var k in counts) out[k] = 1 + Math.log(counts[k]);   // sublinear tf, as in Python
    return out;
  }

  function norm(vec) {
    var sum = 0;
    for (var k in vec) sum += vec[k] * vec[k];
    var mag = Math.sqrt(sum) || 1.0;
    var out = {};
    for (var j in vec) out[j] = vec[j] / mag;
    return out;
  }

  function cos(a, b) {
    if (Object.keys(a).length > Object.keys(b).length) { var t = a; a = b; b = t; }
    var s = 0;
    for (var k in a) if (b[k] !== undefined) s += a[k] * b[k];
    return s;
  }

  /* Project text into the model's space. Unknown terms are dropped, then what remains
   * is normalised — the same order Python uses, which matters for short messages. */
  function vector(text) {
    var idf = B.semantic.idf;
    var t = tf(tokenize(text));
    var kept = {};
    for (var k in t) if (idf[k] !== undefined) kept[k] = t[k] * idf[k];
    return norm(kept);
  }

  var round4 = function (x) { return Math.round(x * 10000) / 10000; };

  function scores(text) {
    var v = vector(text);
    var out = {};
    for (var label in B.semantic.centroids) out[label] = round4(cos(v, B.semantic.centroids[label]));
    return out;
  }

  /* Same contract as app.nlp.semantic.SemanticClassifier.predict. */
  function predict(text) {
    var sc = scores(text);
    var ranked = Object.keys(sc).map(function (k) { return [k, sc[k]]; })
      .sort(function (a, b) { return b[1] - a[1] || (a[0] < b[0] ? -1 : 1); });
    var top = ranked[0];
    var runner = ranked.length > 1 ? ranked[1] : [null, 0];
    var margin = round4(top[1] - runner[1]);
    var known = top[1] > 0;
    return {
      category: known ? top[0] : null,
      similarity: top[1],
      margin: margin,
      // A weak winner is reported as a weak winner; the UI says "unsure" rather than
      // presenting a coin flip as a classification.
      confident: known && top[1] >= B.semantic.min_similarity && margin >= B.semantic.min_margin,
      runner_up: ranked.length > 1 ? { category: runner[0], similarity: runner[1] } : null,
      scores: sc,
      trained_on: B.semantic.trained_on
    };
  }

  /* Nearest labelled sentences, for showing the user why. Uses the same vectors, so a
   * "matched" example is one the model genuinely placed close. */
  function nearest(text, k) {
    var v = vector(text);
    var corpus = B.semantic.corpus;
    var scored = [];
    for (var i = 0; i < corpus.length; i++) {
      scored.push({
        text: corpus[i].text,
        category: corpus[i].category,
        similarity: round4(cos(v, vector(corpus[i].text)))
      });
    }
    scored.sort(function (a, b) { return b.similarity - a.similarity; });
    return scored.slice(0, k || 3);
  }

  /* ---- rule engine, as the service runs it ------------------------------ */

  /* Mirrors app/classifier.classify: weighted keywords, repeat mentions add up, and the
   * confidence is the winner's share of the total. Same arithmetic, same rounding. */
  function ruleClassify(text) {
    var body = String(text || '').toLowerCase();
    var scores = {};
    var total = 0;
    Object.keys(B.rules.category_keywords).forEach(function (cat) {
      var sum = 0;
      var kws = B.rules.category_keywords[cat];
      Object.keys(kws).forEach(function (kw) {
        var count = body.split(kw).length - 1;
        if (count > 0) sum += kws[kw] * count;
      });
      scores[cat] = sum;
      total += sum;
    });
    if (!total) return { category: B.rules.default_category, confidence: 0, scores: scores, matched: [] };
    var best = Object.keys(scores).sort(function (a, b) { return scores[b] - scores[a]; })[0];
    var matched = Object.keys(B.rules.category_keywords[best]).filter(function (kw) {
      return body.indexOf(kw) !== -1;
    });
    return {
      category: best,
      confidence: Math.round(scores[best] / total * 1000) / 1000,
      scores: scores,
      matched: matched
    };
  }

  /* The service routes with the rules and treats the semantic model as a cross-check
   * (app/nlp/semantic.cross_check). Do the same, and fall back to semantics only when the
   * lexicon recognises nothing — that is where the trained model earns its place. */
  function decide(text) {
    var rule = ruleClassify(text);
    var sem = predict(text);
    var ruleTotal = Object.keys(rule.scores).reduce(function (n, k) { return n + rule.scores[k]; }, 0);
    if (ruleTotal > 0) {
      return {
        category: rule.category,
        source: 'rules',
        confidence: rule.confidence,
        agree: sem.category === rule.category,
        rule: rule,
        semantic: sem,
        unsure: rule.confidence < 0.34 && !sem.confident
      };
    }
    if (sem.category && sem.confident) {
      return {
        category: sem.category,
        source: 'semantic',
        confidence: sem.similarity,
        agree: true,
        rule: rule,
        semantic: sem,
        unsure: false
      };
    }
    return {
      category: B.rules.default_category,
      source: 'default',
      confidence: 0,
      agree: false,
      rule: rule,
      semantic: sem,
      unsure: true
    };
  }

  /* Mirrors app/prioritizer.prioritize, including the sender being part of the text. */
  function decidePriority(text, sender) {
    var t = (String(text || '') + ' ' + String(sender || '')).toLowerCase();
    var p = B.rules.priority;
    var has = function (list) { return list.some(function (k) { return t.indexOf(k) !== -1; }); };
    var fired = [];
    var score = 0;
    if (has(p.clinical_context)) { score += 3; fired.push({ signal: 'clinical setting named', weight: 3 }); }
    if (has(p.clinical_equipment)) { score += 3; fired.push({ signal: 'patient-care equipment named', weight: 3 }); }
    if (has(p.safety)) { score += 4; fired.push({ signal: 'safety hazard named', weight: 4 }); }
    if (has(p.urgent)) { score += 2; fired.push({ signal: 'failure or urgency language', weight: 2 }); }
    if (has(p.staffing_critical) && has(p.clinical_context)) {
      score += 3;
      fired.push({ signal: 'staffing shortfall in a clinical area', weight: 3 });
    }
    if (has(p.routine)) { score -= 2; fired.push({ signal: 'routine administrative language', weight: -2 }); }
    if (t.indexOf('high') !== -1 || t.indexOf('emergency') !== -1) {
      score += 1;
      fired.push({ signal: 'escalation word', weight: 1 });
    }
    return {
      priority: score >= 5 ? 'High' : (score >= 2 ? 'Medium' : 'Low'),
      score: score,
      signals: fired
    };
  }

  /* ---- tone ------------------------------------------------------------- */
  var URGENT_IND = ['urgent', 'urgently', 'immediately', 'emergency', 'critical', 'life-threatening',
    'not working', 'will not start', 'down', 'danger', 'unsafe', 'asap', 'unacceptable', 'nearly lost'];
  var FRIENDLY_IND = ['hi', 'hello', 'hey', 'please help', 'could you please', 'thank you', 'thanks',
    'i would appreciate', 'kindly'];

  function tone(text) {
    var t = String(text || '').toLowerCase();
    var word = function (k) {
      return new RegExp('\\b' + k.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '\\b').test(t);
    };
    var hitUrgent = URGENT_IND.filter(word);
    var hitFriendly = FRIENDLY_IND.filter(word);
    return {
      tone: hitUrgent.length ? 'urgent' : (hitFriendly.length ? 'friendly' : 'formal'),
      evidence: hitUrgent.concat(hitFriendly)
    };
  }

  /* ---- patient-data screen ---------------------------------------------- */
  var COMPILED = null;
  function compilePhi() {
    if (COMPILED) return COMPILED;
    COMPILED = B.phi.patterns.map(function (p) {
      return {
        rule: p.rule, severity: p.severity, why: p.why,
        rx: new RegExp(p.regex, p.ignorecase ? 'gi' : 'g')
      };
    });
    return COMPILED;
  }

  function cleanNameHit(rule, text) {
    if (rule !== 'named_person' && rule !== 'named_staff') return true;
    var words = String(text).trim().split(/\s+/);
    var tail = (words[words.length - 1] || '').replace(/[.,;:]+$/, '');
    return B.phi.not_names.indexOf(tail) === -1;
  }

  /* Same rule set, same severities, same reasons as app/nlp/phi.detect. */
  function phiScan(text) {
    var body = String(text || '');
    var hits = [];
    compilePhi().forEach(function (p) {
      var m;
      p.rx.lastIndex = 0;
      while ((m = p.rx.exec(body)) !== null) {
        if (m[0] === '') { p.rx.lastIndex++; continue; }
        if (!cleanNameHit(p.rule, m[0])) continue;
        hits.push({
          rule: p.rule, severity: p.severity, why: p.why,
          match: m[0].slice(0, 80), span: [m.index, m.index + m[0].length]
        });
      }
    });
    hits.sort(function (a, b) { return a.span[0] - b.span[0]; });
    return {
      flags: hits,
      blocked: hits.some(function (h) { return h.severity === 'block'; }),
      review: hits.some(function (h) { return h.severity === 'review'; })
    };
  }

  /* Replace what must not be stored, keeping the sentence readable. */
  function phiRedact(text) {
    var out = String(text || '');
    phiScan(out).flags.forEach(function () { /* positions shift as we replace; rescan below */ });
    var hits = phiScan(out).flags.slice().sort(function (a, b) { return b.span[0] - a.span[0]; });
    hits.forEach(function (h) {
      out = out.slice(0, h.span[0]) + '[redacted]' + out.slice(h.span[1]);
    });
    return out.replace(/\[redacted\](\s*\[redacted\])+/g, '[redacted]');
  }

  var API = {
    init: init,
    tokenize: tokenize,
    vector: vector,
    scores: scores,
    predict: predict,
    ruleClassify: ruleClassify,
    decide: decide,
    decidePriority: decidePriority,
    nearest: nearest,
    tone: tone,
    phiScan: phiScan,
    phiRedact: phiRedact
  };
  root.MedOpsSemantic = API;
})(typeof window !== 'undefined' ? window : globalThis);
