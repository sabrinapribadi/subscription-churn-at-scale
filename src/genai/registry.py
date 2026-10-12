"""Versioned prompts, loaded from src/genai/prompts/<name>.<version>.yaml."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

PROMPTS = Path(__file__).parent / "prompts"


@dataclass(frozen=True)
class Prompt:
    name: str
    version: str
    system: str
    user: str

    def render(self, facts: dict) -> tuple[str, str]:
        return self.system.format(**facts), self.user.format(**facts)


@lru_cache
def load_prompt(name: str, version: str = "v1") -> Prompt:
    d = yaml.safe_load((PROMPTS / f"{name}.{version}.yaml").read_text())
    return Prompt(d["name"], d["version"], d["system"], d["user"])
