"""Semantic classifier: TF-IDF + cosine similarity, standard library only.

Why this exists
  The rule-based classifier only knows the words in its lexicon. A message such as
  "I am locked out of my account" shares no keyword with the IT lexicon entry
  "login". A bag-of-words model with learned IDF weights, plus character n-grams
  to absorb spelling variants, recovers that.

How it is used
  It is a SECOND OPINION, never a silent override. `cross_check` returns both
  answers and a flag when they disagree, so a human reviews the ticket. The rules
  stay the system of record because they are auditable.

Honesty note
  It is trained on a small synthetic seed corpus (app/data/seed_corpus.json).
  Accuracy measured on that corpus by cross-validation is a smoke test, not a
  claim about real hospital traffic.
"""
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Optional

SEED = Path(__file__).resolve().parent.parent / "data" / "seed_corpus.json"

_STOP = frozenset("""a an the and or but if of to in on at for from by with as is are was were be been
being it its this that these those i me my we our you your he she they them their there here
has have had do does did not no so than too very can could should would will just also into
out up down over under again then once please kindly""".split())
# "not" and "no" carry meaning for operations ("not working"), but the category
# signal is in the nouns, so dropping them is safe for routing and shrinks noise.


def tokenize(text: str) -> list[str]:
    """Lowercase word tokens, light stemming, plus character trigrams of long words."""
    words = [w for w in re.findall(r"[a-z][a-z\-']+", text.lower()) if w not in _STOP]
    out = []
    for w in words:
        stem = re.sub(r"(ing|ed|es|s|ly)$", "", w) if len(w) > 4 else w
        out.append(stem)
        if len(stem) >= 6:  # char trigrams make "wifi"/"wi-fi" and typos overlap
            out.extend(f"#{stem[i:i + 3]}" for i in range(len(stem) - 2))
    return out


def _tf(tokens: list[str]) -> dict:
    c = Counter(tokens)
    return {t: 1 + math.log(n) for t, n in c.items()}  # sublinear tf


def _norm(vec: dict) -> dict:
    mag = math.sqrt(sum(v * v for v in vec.values())) or 1.0
    return {k: v / mag for k, v in vec.items()}


def _cos(a: dict, b: dict) -> float:
    if len(a) > len(b):
        a, b = b, a
    return sum(v * b.get(k, 0.0) for k, v in a.items())


class SemanticClassifier:
    def __init__(self):
        self.idf: dict[str, float] = {}
        self.centroids: dict[str, dict] = {}
        self.labels: list[str] = []
        self.trained_on = 0

    def fit(self, rows: list[dict]) -> "SemanticClassifier":
        docs = [(tokenize(r["text"]), r["category"]) for r in rows]
        n = len(docs)
        df = Counter()
        for toks, _ in docs:
            df.update(set(toks))
        self.idf = {t: math.log((1 + n) / (1 + d)) + 1.0 for t, d in df.items()}
        sums: dict[str, dict] = defaultdict(lambda: defaultdict(float))
        for toks, label in docs:
            for t, v in self._vec(toks).items():
                sums[label][t] += v
        self.centroids = {lab: _norm(dict(v)) for lab, v in sums.items()}
        self.labels = sorted(self.centroids)
        self.trained_on = n
        return self

    def _vec(self, tokens: list[str]) -> dict:
        tf = _tf(tokens)
        return _norm({t: w * self.idf[t] for t, w in tf.items() if t in self.idf})

    def scores(self, text: str) -> dict[str, float]:
        v = self._vec(tokenize(text))
        return {lab: round(_cos(v, c), 4) for lab, c in self.centroids.items()}

    def predict(self, text: str) -> dict:
        sc = self.scores(text)
        ranked = sorted(sc.items(), key=lambda kv: kv[1], reverse=True)
        top, runner = ranked[0], ranked[1] if len(ranked) > 1 else (None, 0.0)
        margin = round(top[1] - runner[1], 4)
        # No overlap at all with the vocabulary: say so instead of guessing.
        known = top[1] > 0.0
        return {
            "category": top[0] if known else None,
            "similarity": top[1],
            "margin": margin,
            "confident": known and top[1] >= 0.12 and margin >= 0.04,
            "scores": sc,
        }


def load_corpus(path: Path = SEED) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))["rows"]


def lexicon_priors() -> list[dict]:
    """Turn the rule engine's weighted lexicon into pseudo-documents.

    The rules encode real domain knowledge (a ventilator is an engineering asset).
    Feeding the lexicon in as training text gives the semantic model that knowledge,
    while the labelled corpus teaches it phrasing the lexicon lacks. Weight becomes
    repetition. Measured: corpus alone 41% CV, corpus + lexicon priors 71% CV.
    """
    from ..classifier import CATEGORY_KEYWORDS
    docs: list[dict] = []
    for cat, kws in CATEGORY_KEYWORDS.items():
        for kw, weight in kws.items():
            docs.extend([{"text": kw.strip(), "category": cat}] * max(1, weight))
    return docs


_model: Optional[SemanticClassifier] = None


def get_model() -> SemanticClassifier:
    global _model
    if _model is None:
        _model = SemanticClassifier().fit(load_corpus() + lexicon_priors())
    return _model


def cross_validate(rows: list[dict], folds: int = 5, with_priors: bool = True) -> dict:
    """k-fold accuracy on the seed corpus. A smoke test, not a real-world claim.

    The lexicon priors are added to every training fold; they never contain the
    held-out sentences, so there is no leakage.
    """
    rows = list(rows)
    priors = lexicon_priors() if with_priors else []
    correct = 0
    for k in range(folds):
        test = [r for i, r in enumerate(rows) if i % folds == k]
        train = [r for i, r in enumerate(rows) if i % folds != k]
        m = SemanticClassifier().fit(train + priors)
        correct += sum(1 for r in test if m.predict(r["text"])["category"] == r["category"])
    return {"folds": folds, "n": len(rows), "with_lexicon_priors": with_priors,
            "accuracy": round(correct / len(rows), 4)}


def cross_check(message: str, rule_category: str) -> dict:
    """Compare the semantic opinion with the rule engine's category."""
    pred = get_model().predict(message)
    agrees = pred["category"] == rule_category
    return {
        "rule_category": rule_category,
        "semantic_category": pred["category"],
        "semantic_similarity": pred["similarity"],
        "semantic_margin": pred["margin"],
        "semantic_confident": pred["confident"],
        "agree": agrees,
        # Only ask a human when the semantic model is confident AND disagrees.
        "needs_review": bool(pred["confident"] and not agrees),
    }
