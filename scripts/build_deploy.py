"""Assemble the public demo bundle for a free serverless host (ADR-010, rules R19 and R20).

    python scripts/build_deploy.py [--out build/subscription-churn-at-scale]

Holds only the light serving code, the checksummed snapshot and four dependencies (FastAPI, MCP, pydantic, PyYAML):
no model files, no member rows, no API key. `app.py` is the entrypoint for Vercel's Python runtime.
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CODE = ["src/__init__.py", "src/services/__init__.py", "src/services/contracts.py", "src/services/public.py", "src/services/scenarios.py",
        "src/genai/__init__.py", "src/genai/tools.py", "src/gateway/__init__.py", "src/gateway/mcp_server.py"]
REQUIREMENTS = "fastapi==0.143.0\nmcp==2.3.0\npydantic>=2.7\npyyaml>=6.0\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "build" / "subscription-churn-at-scale"))
    out = Path(ap.parse_args().out)
    snap, sha = ROOT / "deploy" / "public_snapshot.json", ROOT / "deploy" / "public_snapshot.sha256"
    if hashlib.sha256(snap.read_bytes()).hexdigest() != sha.read_text().split()[0]:
        raise SystemExit("snapshot does not match deploy/public_snapshot.sha256")
    shutil.rmtree(out, ignore_errors=True)
    for f in CODE:
        (out / f).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / f, out / f)
    (out / "deploy").mkdir(); shutil.copy(snap, out / "deploy" / snap.name)
    (out / "requirements.txt").write_text(REQUIREMENTS)
    (out / "app.py").write_text('"""Vercel entrypoint."""\nfrom src.services.public import app  # noqa: F401\n')
    (out / ".python-version").write_text("3.12\n")
    print(f"bundle: {out} ({sum(p.stat().st_size for p in out.rglob('*') if p.is_file()) / 1e6:.2f} MB)")


if __name__ == "__main__":
    main()
