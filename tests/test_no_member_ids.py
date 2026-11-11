"""Competition data terms (README, ADR-010): no member id may appear in committed results, pages or the demo snapshot."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MSNO = re.compile(r"[A-Za-z0-9+/]{43}=")          # KKBox member ids: 44-character base64 strings


def test_no_member_id_in_committed_outputs_pages_or_snapshot():
    files = [*ROOT.glob("data/outputs/*.json"), *ROOT.glob("docs/**/*.html"), *ROOT.glob("docs/**/*.js"), ROOT / "deploy" / "public_snapshot.json"]
    hits = {str(f.relative_to(ROOT)): len(MSNO.findall(f.read_text(errors="ignore"))) for f in files if f.exists()}
    assert not {k: v for k, v in hits.items() if v}, hits
