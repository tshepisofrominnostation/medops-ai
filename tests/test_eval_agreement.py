"""S5-1: inter-rater reliability tool. Proves the tool measures agreement, not agreement we hoped for."""
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from scripts.eval_agreement import cohen_kappa, band, summarise  # noqa: E402


def _write(tmp_path, name, rows):
    p = tmp_path / name
    p.write_text(json.dumps(rows), encoding="utf-8")
    return str(p)


def test_perfect_agreement_is_kappa_one(tmp_path):
    a = _write(tmp_path, "a.json", [{"case_id": f"c{i}", "label": "pass"} for i in range(6)])
    b = _write(tmp_path, "b.json", [{"case_id": f"c{i}", "label": "pass"} for i in range(6)])
    result = summarise(a, b)
    assert result["percent_agreement"] == 100.0
    assert result["kappa"] == 1.0
    assert "good" in result["verdict"]


def test_opposite_labels_both_categories_is_kappa_minus_one(tmp_path):
    # Agreement is at chance level, so kappa bottoms out at -1.
    a = _write(tmp_path, "a.json", [{"case_id": f"c{i}", "label": "pass" if i < 2 else "fail"} for i in range(4)])
    b = _write(tmp_path, "b.json", [{"case_id": f"c{i}", "label": "fail" if i < 2 else "pass"} for i in range(4)])
    from scripts.eval_agreement import load
    kappa, agree, n = cohen_kappa(load(a), load(b))
    assert (agree, n) == (0, 4)
    assert kappa == -1.0
    assert "poor" in band(kappa)


def test_degenerate_single_category_each_gives_zero_not_minus_one(tmp_path):
    # Each reviewer used one category only, so chance agreement is 0 and kappa is 0:
    # this is not evidence of agreement, and the tool must not claim otherwise.
    a = _write(tmp_path, "a.json", [{"case_id": f"c{i}", "label": "pass"} for i in range(4)])
    b = _write(tmp_path, "b.json", [{"case_id": f"c{i}", "label": "fail"} for i in range(4)])
    from scripts.eval_agreement import load
    kappa, agree, n = cohen_kappa(load(a), load(b))
    assert (agree, n) == (0, 4)
    assert kappa == 0.0


def test_partial_agreement_and_unmatched_cases(tmp_path):
    a = _write(tmp_path, "a.json", [
        {"case_id": "c1", "label": "pass"}, {"case_id": "c2", "label": "fail"},
        {"case_id": "c3", "label": "pass"}, {"case_id": "c4", "label": "fail"}])
    b = _write(tmp_path, "b.json", [
        {"case_id": "c1", "label": "pass"}, {"case_id": "c2", "label": "fail"},
        {"case_id": "c3", "label": "fail"}])
    result = summarise(a, b)
    # c4 exists only in A: it must be excluded from the comparison, not silently agreed.
    assert result["compared"] == 3
    assert result["agreed"] == 2
    assert result["unmatched"] == {"only_in_a": 1, "only_in_b": 0}
    assert -1.0 <= result["kappa"] <= 1.0


def test_cli_reports_and_exits_zero(tmp_path):
    a = _write(tmp_path, "a.json", [{"case_id": "c1", "label": "pass"}, {"case_id": "c2", "label": "fail"}])
    b = _write(tmp_path, "b.json", [{"case_id": "c1", "label": "pass"}, {"case_id": "c2", "label": "fail"}])
    out = subprocess.run([sys.executable, "scripts/eval_agreement.py", a, b],
                         cwd=REPO, capture_output=True, text=True)
    assert out.returncode == 0
    assert "kappa 1.0" in out.stdout


def test_missing_case_id_is_rejected(tmp_path):
    bad = _write(tmp_path, "bad.json", [{"label": "pass"}])
    out = subprocess.run([sys.executable, "scripts/eval_agreement.py", bad, bad],
                         cwd=REPO, capture_output=True, text=True)
    assert out.returncode == 1
    assert "case_id" in out.stdout
