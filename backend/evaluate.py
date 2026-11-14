"""Accuracy check for the translation pipeline, no frontend needed.

    python -m backend.evaluate              # against the real model (needs .env)
    python -m backend.evaluate --offline    # phrase bank and fallback only, no key needed

Runs every sentence in backend/eval_sentences.json and scores what can be checked without a fluent
signer: question type, emotion, key signs present, fully signed, speed. Writes a review sheet for a
signer to backend/data/eval-<time>.csv (git-ignored). Sign order and grammar still need a human.
"""
import argparse
import csv
import json
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

from backend.translate import translate

HERE = Path(__file__).parent
SENTENCES = HERE / "eval_sentences.json"
OUT_DIR = HERE / "data"
FAST_SECONDS = 3.0  # the README's hour-16 pivot test: fully signed in under three seconds


def evaluate(sentences, **translate_kw):
    """Returns (rows, summary). translate_kw goes to translate(), e.g. offline=True or a fake model."""
    rows = []
    for s in sentences:
        expect = s.get("expect", {})
        start = time.monotonic()
        r = translate(s["text"], face_emotions=s.get("face_emotions"), **translate_kw)
        seconds = time.monotonic() - start
        glosses = [x["gloss"] for x in r["signs"]]
        fingerspelled = [x["gloss"] for x in r["signs"] if not x["known"]]
        rows.append({
            "text": s["text"],
            "signs": " ".join(g + ("*" if g in fingerspelled else "") for g in glosses),
            "face": r["face"],
            "face_ok": r["face"] == expect["face"] if "face" in expect else None,
            "emotion": r["emotion"],
            "emotion_ok": r["emotion"] == expect["emotion"] if "emotion" in expect else None,
            "expected_signs": len(expect.get("signs", [])),
            "missing_signs": " ".join(g for g in expect.get("signs", []) if g not in glosses),
            "fingerspelled": len(fingerspelled),
            "fully_signed": not r["unsure"] and not fingerspelled,
            "source": r["source"],
            "unsure": r["unsure"],
            "meaning": r["meaning"],
            "seconds": round(seconds, 2),
        })
    return rows, summarize(rows)


def summarize(rows):
    def rate(key):
        scored = [r[key] for r in rows if r[key] is not None]
        return f"{sum(scored)}/{len(scored)}" if scored else "n/a"

    expected = sum(r["expected_signs"] for r in rows)
    missing = sum(len(r["missing_signs"].split()) for r in rows)
    times = [r["seconds"] for r in rows] or [0]
    return {
        "sentences": len(rows),
        "source": dict(Counter(r["source"] for r in rows)),
        "unsure": sum(r["unsure"] for r in rows),
        "question type correct": rate("face_ok"),
        "emotion correct": rate("emotion_ok"),
        "key signs present": f"{expected - missing}/{expected}",
        "fully signed": sum(r["fully_signed"] for r in rows),
        "fully signed in under 3 s (pivot test)": sum(r["fully_signed"] and r["seconds"] < FAST_SECONDS for r in rows),
        "average seconds": round(sum(times) / len(times), 2),
        "slowest seconds": max(times),
    }


def write_review_sheet(rows, out_dir=OUT_DIR):
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"eval-{datetime.now():%Y%m%d-%H%M%S}.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[*rows[0], "signer_review"])
        writer.writeheader()
        writer.writerows(rows)
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--offline", action="store_true", help="phrase bank and fallback only, no model calls")
    parser.add_argument("--file", type=Path, default=SENTENCES, help="sentences to run (default: eval_sentences.json)")
    args = parser.parse_args()

    rows, summary = evaluate(json.loads(args.file.read_text(encoding="utf-8")), offline=args.offline)
    for r in rows:
        flags = " ".join(f for f, bad in (("FACE", r["face_ok"] is False), ("EMOTION", r["emotion_ok"] is False),
                                          ("MISSING:" + r["missing_signs"], bool(r["missing_signs"])),
                                          ("UNSURE", r["unsure"])) if bad)
        print(f"{r['seconds']:>5}s  {r['source']:<11} {r['text'][:32]:<32} -> {r['signs'][:40]:<40} {flags}")
    print()
    for k, v in summary.items():
        print(f"{k:<40} {v}")
    if not args.offline and summary["source"].get("fallback") == len(rows):
        print("\nEvery sentence used the fallback: the model was never reached. Check .env "
              "(LLM_PROVIDER, the API key, LLM_MODEL) and the warnings above.")
    print(f"\nReview sheet for a fluent signer: {write_review_sheet(rows)}")


if __name__ == "__main__":
    main()
