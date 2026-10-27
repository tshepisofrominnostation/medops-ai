# MedOps AI — Team Sprint Plan

Four one-week sprints, Mon 26 Oct to Fri 20 Nov 2026 (the 8-week bootcamp outline compressed 2:1). Team of four.

Stand-up daily 08:30 (15 min). Midday checkpoint 12:30. Push by 16:00. Review + retro Fridays 15:00, notes on the sprint milestone issue.

## Team
- **Tshepiso (tshepisofrominnostation)** — Scrum Master / Developer: process, engine, delivery
- **Xoliswa-Dee, Anastacia202, Avuyile-Plaatjie** — Developers / QA: owners picked at Monday planning
- Roles are confirmed at Sprint 1 planning, Monday 26 Oct 08:30.

## Starting point (honest)
Already shipped in Week 1 (by the SM): the full classification engine — parser, classifier, prioritiser, summariser, assigner, persistence, FastAPI, 8 passing tests, live console. Sprint 1 finishes the sprint: responses, the 20-case test set, API hardening, onboarding.

## Sprint 1 (26–30 Oct): Core engine + responses
Goal: message in -> classified -> response drafted -> persisted, proven on 20 cases.

## Sprint 2 (2–6 Nov): Data analysis + reporting
Goal: the hospital sees what is happening. Analytics service, dashboard, one-click PDF report per department.

## Sprint 3 (9–13 Nov): Prediction + governance
Goal: the platform looks forward and checks itself. Surge forecast with an honest error metric; compliance screeners on generated responses (no PHI patterns); risk report with three real findings.

## Sprint 4 (16–20 Nov): Automate, deploy, present
Goal: deployed, documented, demo-ready. Assignment alerts, hosted API, final docs, business case deck, mock panel. Feature freeze Wed 12:00.

## Working agreement
- One branch per story (feature/...), PR to protected main, one review before merge.
- Definition of Done: tests pass, README updated where behaviour changed, demo-able.
- Descope order under pressure: forecast sophistication, PDF report polish, alert channel richness. Never cut: engine correctness, tests, deployment, docs.
