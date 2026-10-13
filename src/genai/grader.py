"""Rule-based grounding grader for agent notes (ADR-006). Deterministic, so CI can gate on it."""

from __future__ import annotations

import re

from src.genai.dictionary import SENSITIVE, _LABELS

ACTIONS = ["help switch to auto-renew", "send a re-engagement message", "offer a discount on the next plan",
           "send a renewal reminder", "no call needed"]
MAX_WORDS = 90
_NUM = re.compile(r"\d+(?:[.,]\d+)?")
_SENSITIVE_WORDS = re.compile(r"\b(age|aged|gender|male|female|man|woman|city)\b", re.I)


def _numbers(text: str) -> set[str]:
    return {n.replace(",", "") for n in _NUM.findall(text)}


def mentions_any(text: str, words: list[str]) -> bool:
    """Whole-word match, so a banned "19" does not fire inside "2190"."""
    return any(re.search(rf"(?<![\w.]){re.escape(w)}(?![\w])", text, re.I) for w in words)


def grade(text: str, facts: dict) -> dict[str, bool]:
    allowed = set()
    for v in facts["allowed_number_sources"]:
        allowed |= _numbers(str(v))
    used = _numbers(text)
    words = len(text.split())
    shown = [r["label"].lower() for r in facts["agent_reasons"]]
    other_labels = [lab.lower() for f, (lab, _) in _LABELS.items() if lab.lower() not in shown and f not in SENSITIVE]
    lower = text.lower()
    # remove allowed phrases first: some labels contain others ("auto-renew" ⊂ "share of payments on auto-renew")
    scrubbed = lower
    for phrase in sorted(shown + [facts["action"].lower()], key=len, reverse=True):
        scrubbed = scrubbed.replace(phrase, " ")
    return {
        "numbers_grounded": used <= allowed,
        "top_reason_mentioned": shown[0] in lower if shown else True,
        "no_other_features": not any(lab in scrubbed for lab in other_labels),
        "no_sensitive_attributes": not _SENSITIVE_WORDS.search(text),
        "length_ok": words <= MAX_WORDS,
        "action_ok": lower.rstrip().endswith(f"suggested action: {facts['action']}.".lower()),
    }
