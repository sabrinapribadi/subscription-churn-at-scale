"""Build the public demo snapshot from the real serving artefacts (ADR-010).

    SERVING_DIR=~/data/kkbox/serving python scripts/build_public_snapshot.py     # OPENAI_API_KEY in .env: live notes, else templates

Writes deploy/public_snapshot.json and its SHA-256, after checking that no real member id is in it.
Notes are written once here (about 100 calls, under one US cent); the public host never calls a model.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.genai.explain import Explainer  # noqa: E402
from src.genai.providers import get_provider  # noqa: E402
from src.services.public_snapshot import build  # noqa: E402
from src.services.store import ServingStore  # noqa: E402


def main() -> None:
    cfg = yaml.safe_load((ROOT / "configs" / "default_config.yaml").read_text())
    store = ServingStore(os.path.expanduser(os.environ["SERVING_DIR"]))
    snap = build(store, Explainer(get_provider(cfg["llm"])), built=dt.date.today().isoformat())
    text = json.dumps(snap, separators=(",", ":"))
    leaked = [m for m in store.df.index if m in text]
    if leaked:
        sys.exit(f"refusing to write: {len(leaked)} real member ids found in the snapshot")
    out = ROOT / "deploy" / "public_snapshot.json"
    out.write_text(text)
    (out.with_suffix(".sha256")).write_text(hashlib.sha256(out.read_bytes()).hexdigest() + "  public_snapshot.json\n")
    print({"bytes": len(text), "members": snap["call_grid"]["members"], **snap["notes"]})


if __name__ == "__main__":
    main()
