"""Accuracy check for gloss -> English, no camera needed.

    python -m asl2english.evaluate              # against the real model (needs .env)
    python -m asl2english.evaluate --offline    # deterministic fallback only, no key needed

Runs every child-style gloss sequence in asl2english/eval_understand.json (signs as if already recognised)
and scores what can be checked without a fluent signer: exact intent (the English matches one of the intended
readings, ignoring case and punctuation), question type, unsure rate and speed. Writes a review sheet to
asl2english/data/understand-<time>.csv (git-ignored). Whether the reading is right for real child ASL still
needs a Deaf or fluent signer: this does not measure ASL-grammar correctness.
"""
import argparse
import csv
import json
import os
import re
import tempfile
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

from asl2english.asl_to_english import understand
from backend.llm import LLMUnavailable

HERE = Path(__file__).parent
ITEMS = HERE / "eval_understand.json"
OUT_DIR = HERE / "data"
CHILD = "Maya"


class _Offline:
    def understand(self, **kw):
        raise LLMUnavailable("offline evaluation")


def load_items(path=ITEMS):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _norm(text):
    return " ".join(re.findall(r"[a-z0-9']+", text.lower().replace("\u2019", "'")))


def evaluate(items, *, model=None, offline=False, child_name=CHILD):
    """Returns (rows, summary). model: anything with .understand(**kw), e.g. a fake in tests."""
    model = _Offline() if offline else model
    rows = []
    for it in items:
        confs = it.get("confidences") or [0.9] * len(it["signs"])
        signs = [{"gloss": g, "confidence": c} for g, c in zip(it["signs"], confs)]
        intended = {_norm(t) for t in it["intended"]}
        start = time.monotonic()
        r = understand(signs, it.get("face"), it.get("head_shake"), it.get("emotion"), child_name=child_name, model=model)
        seconds = time.monotonic() - start
        rows.append({
            "signs": " ".join(f"{g}({c:.2f})" if c < 0.9 else g for g, c in zip(it["signs"], confs)),
            "cues": " ".join(x for x in (it.get("face"), "head-shake" if it.get("head_shake") else "", it.get("emotion")) if x),
            "intended": " | ".join(it["intended"]),
            "english": r["english"],
            "alternatives": " | ".join(r["alternatives"]),
            "exact_intent": _norm(r["english"]) in intended,
            "intent_in_alternatives": any(_norm(a) in intended for a in [r["english"], *r["alternatives"]]),
            "is_question": r["is_question"],
            "question_ok": r["is_question"] == it["is_question"] if "is_question" in it else None,
            "unsure": r["unsure"],
            "low_confidence_signs": " ".join(r["low_confidence_signs"]),
            "emotion": r["emotion"],
            "confidence": r["confidence"],
            "source": r["source"],
            "seconds": round(seconds, 2),
        })
    return rows, summarize(rows)


def summarize(rows):
    def rate(key):
        scored = [r[key] for r in rows if r[key] is not None]
        return f"{sum(scored)}/{len(scored)}" if scored else "n/a"

    times = [r["seconds"] for r in rows] or [0]
    return {
        "items": len(rows),
        "source": dict(Counter(r["source"] for r in rows)),
        "exact intent": rate("exact_intent"),
        "intent in english or alternatives": rate("intent_in_alternatives"),
        "question type correct": rate("question_ok"),
        "unsure": rate("unsure"),
        "average seconds": round(sum(times) / len(times), 2),
        "slowest seconds": max(times),
    }


def write_review_sheet(rows, out_dir=OUT_DIR):
    """CSV for a fluent signer, written atomically (readers never see a half-written file)."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"understand-{datetime.now():%Y%m%d-%H%M%S}.csv"
    fd, tmp = tempfile.mkstemp(dir=out_dir, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=[*rows[0], "signer_review"])
            writer.writeheader()
            writer.writerows(rows)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--offline", action="store_true", help="deterministic fallback only, no model calls")
    parser.add_argument("--file", type=Path, default=ITEMS, help="items to run (default: eval_understand.json)")
    args = parser.parse_args()

    rows, summary = evaluate(load_items(args.file), offline=args.offline)
    for r in rows:
        flags = " ".join(f for f, bad in (("INTENT", not r["exact_intent"]), ("QUESTION", r["question_ok"] is False),
                                          ("UNSURE", r["unsure"])) if bad)
        print(f"{r['seconds']:>5}s  {r['source']:<8} {r['signs'][:30]:<30} -> {r['english'][:44]:<44} {flags}")
    print()
    for k, v in summary.items():
        print(f"{k:<36} {v}")
    if not args.offline and summary["source"].get("fallback") == len(rows):
        print("\nEvery item used the fallback: the model was never reached. Check .env "
              "(LLM_PROVIDER, the API key, LLM_MODEL) and the warnings above.")
    print("\nExact intent is a rough automatic match against the readings we wrote; it does not check ASL grammar.")
    print(f"Review sheet for a fluent signer: {write_review_sheet(rows)}")


if __name__ == "__main__":
    main()
