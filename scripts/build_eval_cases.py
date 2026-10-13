"""Grow the LLM evaluation set with real scored members (ADR-006).

    python scripts/build_eval_cases.py            # needs SERVING_DIR (default ~/data/kkbox/serving)

Keeps the hand-written edge cases (source "edge") and replaces the real ones (source "real"):
16 members per risk level, spread across top reasons, fixed seed. Age or city ranks in a member's
top-5 reasons for only ~2% of members, so 2 such members per level are included on purpose to test
that hidden demographic reasons never reach the note. Member ids are replaced by
labels, so no dataset ids are stored. Expected actions for real cases come from the action rule
(a regression pin); the edge cases carry human-set actions.
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.genai.explain import build_facts  # noqa: E402
from src.services.store import ServingStore  # noqa: E402

CASES = Path("tests/llm_eval/cases.json")
PER_LEVEL, SENSITIVE_PER_LEVEL, POOL, SCAN, SEED = 16, 2, 800, 30_000, 2017


def must_not_mention(reasons, facts) -> list[str]:
    allowed = " ".join(str(v) for v in facts["allowed_number_sources"])
    out = []
    for r in reasons.reasons:
        if r.shown_to_agent:
            continue
        out.append(r.label)
        v = r.value.replace("code ", "")
        if re.fullmatch(r"\d+", v) and not re.search(rf"(?<![\w.]){v}(?![\w])", allowed):
            out.append(v)
        elif v in ("male", "female"):
            out.append(v)
    return out


def main() -> None:
    store = ServingStore(os.path.expanduser(os.environ.get("SERVING_DIR", "~/data/kkbox/serving")))
    rng = np.random.default_rng(SEED)
    level = np.where(store.df["_p"] >= 0.30, "high", np.where(store.df["_p"] >= 0.10, "medium", "low"))
    real = []
    for lv in ("low", "medium", "high"):
        ids = store.df.index[level == lv].to_numpy()
        ids = rng.choice(ids, size=min(SCAN, len(ids)), replace=False)  # TreeSHAP on every member is too slow
        pool = store.df.loc[ids, store.features]
        contrib = store.booster.predict(pool, pred_contrib=True)[:, :-1]
        top5 = np.argsort(-np.abs(contrib), axis=1)[:, :5]
        sens = [store.features.index(f) for f in ("age", "gender", "city") if f in store.features]
        has_sens = np.isin(top5, sens).any(axis=1)
        picked = [(m, store.reasons(m)) for m in rng.choice(ids[has_sens], size=SENSITIVE_PER_LEVEL, replace=False)]
        groups = defaultdict(list)  # top reason shown to the agent -> members
        for m in rng.choice(ids[~has_sens], size=min(POOL, int((~has_sens).sum())), replace=False):
            rs = store.reasons(m)
            shown = [r for r in rs.reasons if r.shown_to_agent]
            if shown:
                groups[shown[0].feature].append((m, rs))
        while len(picked) < PER_LEVEL and any(groups.values()):  # round-robin over top reasons, biggest groups first
            for f in sorted(groups, key=lambda g: -len(groups[g])):
                if groups[f] and len(picked) < PER_LEVEL:
                    picked.append(groups[f].pop(0))
        for i, (m, rs) in enumerate(picked, 1):
            s = store.score(m)
            facts = build_facts(s, rs)
            real.append({"id": f"real_{lv}_{i:02d}", "source": "real", "p": round(s.churn_probability, 4), "risk": s.risk_level,
                         "value": round(s.member_value, 2), "expiry": s.expiry_date,
                         "reasons": [r.model_dump() for r in rs.reasons], "expected_action": facts["action"],
                         "must_not_mention": must_not_mention(rs, facts)})
    edge = [dict(c, source="edge") for c in json.loads(CASES.read_text()) if c.get("source", "edge") == "edge"]
    CASES.write_text(json.dumps(edge + real, indent=1) + "\n")
    top = defaultdict(int)
    for c in real:
        top[next(r["label"] for r in c["reasons"] if r["shown_to_agent"])] += 1
    print(f"{len(edge)} edge + {len(real)} real cases; with a hidden sensitive reason: "
          f"{sum(any(not r['shown_to_agent'] for r in c['reasons']) for c in real)}")
    print("top reasons:", dict(sorted(top.items(), key=lambda kv: -kv[1])))
    print("actions:", {a: sum(c["expected_action"] == a for c in real) for a in sorted({c["expected_action"] for c in real})})


if __name__ == "__main__":
    main()
