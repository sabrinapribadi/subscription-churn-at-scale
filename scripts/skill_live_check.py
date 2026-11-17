"""Live check for the agent skill (R24): the client reaches the deployed API and the facts the eval graders rely on still hold.

    python scripts/skill_live_check.py [--base URL]
If the snapshot is rebuilt and a fact changes, this fails so the graders in skills/churn-call-planner/evals are updated, not left stale.
"""
import json
import subprocess
import sys
from pathlib import Path

CLIENT = Path(__file__).resolve().parents[1] / "skills/churn-call-planner/scripts/churn.py"
base = sys.argv[sys.argv.index("--base") + 1] if "--base" in sys.argv else "https://subscription-churn-at-scale.vercel.app"


def call(*args):
    r = subprocess.run([sys.executable, str(CLIENT), "--base", base, *args], capture_output=True, text=True, timeout=180, check=False)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


ab = call("about")
assert ab["test_cohort"]["members"] == 862158, ab
cl = call("call-list", "--share", "0.1")["summary"]
assert cl["members_called"] == 86215 and round(cl["expected_value_at_risk"]) == 60918657, cl
w = call("what-if")["profit_at_10pct"]
assert round(w["expected_value"], -3) == 12431000 and round(w["probability"], -3) == 12408000 and round(w["lambdamart"], -3) == 9699000, w
e = call("explain", "demo-001")
assert round(e["score"]["churn_probability"], 2) == 0.17 and e["score"]["risk_level"] == "medium" and round(e["score"]["member_value"]) == 1813, e["score"]
assert [r["label"] for r in e["reasons"]][:2] == ["days since last payment", "payment method"], e["reasons"]
assert call("score", "Wk8vF3qZ+abc=").get("not_found") is True                   # real-looking ids are never served
print(f"skill live check passed against {base}")
