# MedOps AI — Risk evaluation report (S3-3)

Date: 6 November 2026 · Owner: Tshepiso Freddy Thosago (Scrum Master)
Method: we ran our own platform against its own artefacts and recorded what broke.
Every number below is reproducible with `PYTHONPATH=. python3 scripts/risk_audit.py`
and the commands quoted with each finding.

We looked for problems. These are the four we found, ordered by how badly they
could hurt a hospital that trusted us.

---

## R1 — Our 100% evaluation score is not an accuracy claim (High)

**What we measured.** All 20 cases in `tests/data/evaluation_set.json` classify
correctly: 20 right, 0 wrong.

**Why that is a risk, not a result.** The same person wrote the classifier and the
evaluation set, in the same week, using the same vocabulary. A perfect score on
home-made tests measures agreement with the author's phrasing, not accuracy on a
real ward. Presenting 100% to a hospital would be misleading.

**Evidence.**
```
probe: classifier_accuracy  right: 20  wrong: 0  pct: 100.0
```

**Mitigation.** Quote it as "20 of 20 on our own hand-written set", never as
accuracy. The honest next step is 200 real, ticket-level labels written by someone
who has never seen the classifier, then report the confusion matrix.
**Owner:** Tshepiso. **Due:** first week of any pilot, before any accuracy claim.

---

## R2 — Undated tickets are counted but invisible (Medium)
**[UPDATED — 6 Nov, `week2-baseline-rebuild`]** The insight layer now counts undated
tickets at scope level and reports them as a data-quality finding, so they can no
longer vanish. `build_analytics` still windows them out (by design: an undated ticket
cannot be placed in a week), but `GET /insights` states the number explicitly.
Regression test: `tests/test_insights.py::test_undated_tickets_are_disclosed`.

**What we measured.** Two records: one with a timestamp, one without.
`total_tickets` reports 2, but `by_day` contains a single day with a count of 1.

**Why it matters.** The dashboard headline and the trend chart contradict each
other. A department reading the PDF sees a total that the chart cannot account
for, and nobody knows which number to trust. Worse, it fails silently.

**Evidence.**
```
probe: undated_records  records: 2  counted: 2
by_day: [{ "date": "2026-11-05", "count": 1 }]
```

**Mitigation.** Add `undated_tickets` to the analytics contract so the gap is
explicit, and surface it on the dashboard as "N tickets without a date". Consumers
(S2-2, S2-3) must read the field, so the contract change ships with a version note.
**Owner:** Tshepiso (contract), Avuyile (dashboard display). **Due:** next sprint.

---

## R3 — The forecast is no better than a flat average on noisy data (Medium)
**[UPDATED — 6 Nov]** The report and console suppress the backtest error until there
are 14+ days of history, because a 2-point backtest (all that 6 days of data supports)
produces a misleading 0.00. Below that the output says no error margin can be quoted.

**What we measured.** Three synthetic series through `app/forecast.py`:

| Series | Backtest MAE | Naive last-5 average | Model error vs naive level |
|---|---|---|---|
| flat | 0.00 | 5.0 | 0 |
| noisy (1–9 random) | 2.62 | 5.0 | 3.0 |
| trending | 0.23 | 7.4 | 0 |

**Why it matters.** On a trending series a straight line is enough. On noisy data
the model is *worse* than simply averaging the last week, which is the cheapest
forecast available. Selling this as "prediction" would overstate what it does.

**Evidence.** `probe: forecast_vs_naive` in the audit output above.

**Mitigation.** Publish `backtest_mae` next to every forecast (already done) and
label the feature "planning aid, not a prediction". If a real use case needs
accuracy, test seasonal baselines on real history before tuning anything.
**Owner:** Tshepiso. **Due:** before the panel, in the deck wording.

---

## R4 — The compliance screen misses all semantic PHI (Critical)
**[UPDATED — 6 Nov, `week2-baseline-rebuild`]** `app/nlp/phi.py` adds a
composition-based detector (person reference + location, relationship or health
context). The six phrasings below are now permanently tested in
`tests/test_phi_semantic.py` and **all six are caught, with 0 of 20 of the system's own
generated replies falsely flagged**. Six further unseen phrasings are also caught.
This raises the floor; it does not make the screen a guarantee. It remains heuristic,
can miss unusual names and non-English text, and **human review of drafted replies is
still required**. The API now returns that disclaimer on every screen result.

**What we measured.** Six phrasings that carry patient-identifiable information
without any regex-detectable pattern. The screen caught **0 of 6**.

```
MISSED | Mr Dlamini in bed 12 has been waiting since Monday
MISSED | The lady from the maternity ward whose husband called yesterday
MISSED | Her medical aid, the one ending 8834, will cover it
MISSED | He is on the ARV regimen we discussed
MISSED | The patient who attempted suicide last week
MISSED | Your reference is MED-042 (clean control — correctly not flagged)
```

**Why it is critical.** A name plus a bed number is identifiable health
information. The screen returns "clean", so a reply containing it would be sent
without review. This is a POPIA exposure, not a bug.

**Evidence.** Audit probe `adversarial_phi` (run inline; see chat transcript of
6 Nov) — 0/6 caught. The screen's own tests only cover patterns it already knows,
which is why they all pass.

**Mitigation, in order.**
1. Treat the screen as a *floor*, not a guarantee, and say so in the UI and README.
2. Require human review of every generated reply until item 3 lands.
3. Add name/relationship/location detection (a small gazetteer of ward and bed
   patterns plus a person-name detector) and re-run the 6 adversarial cases as a
   permanent regression test with a floor of 6/6 before the screen may claim
   "clean" on its own.
**Owner:** Xoliswa-Dee (QA) with Tshepiso. **Due:** before any live patient data.

---

## What we deliberately did not claim

- We did not measure clinical safety. We screen for identifiers and advice-shaped
  language, which is not the same thing.
- We did not test under load. Single-user throughput is all we know.
- We did not test non-English messages beyond the tone detector's tolerance.

A platform that lists its weaknesses is more useful to a hospital than one that
reports none.
