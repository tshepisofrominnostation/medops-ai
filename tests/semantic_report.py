"""Reproducible evidence for the numbers quoted about the semantic model.

    python -m tests.semantic_report
"""
from app.classifier import classify
from app.nlp.semantic import cross_validate, load_corpus


def main():
    rows = load_corpus()
    with_priors = cross_validate(rows, with_priors=True)
    without = cross_validate(rows, with_priors=False)
    rules = sum(1 for r in rows if classify(r["text"])[0] == r["category"]) / len(rows)
    print(f"seed corpus: {len(rows)} hand-written sentences, 4 balanced classes")
    print(f"5-fold CV, corpus only          : {without['accuracy']:.3f}")
    print(f"5-fold CV, corpus + lexicon     : {with_priors['accuracy']:.3f}")
    print(f"rule engine, same sentences     : {rules:.3f}")
    print()
    print("The lexicon priors are the rule engine's weighted keywords, so the two")
    print("scores are not independent evidence. A model trained on its own rules")
    print("agrees with them by construction; the honest reading is that the semantic")
    print("layer adds a different view for a human to compare, not a better oracle.")


if __name__ == "__main__":
    main()
