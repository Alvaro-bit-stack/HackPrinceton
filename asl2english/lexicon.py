"""Sign meanings and look-alike pairs from ASL-LEX 2.0 (asl2english/lexicon.json, made by build_lexicon.py).
Missing file: falls back to shared/vocab.json meanings only and no look-alikes, so the app still runs."""
import json
import logging
from pathlib import Path

from backend.translate import VOCAB

PATH = Path(__file__).parent / "lexicon.json"


def load(path=PATH):
    """-> (meanings {gloss: [english...]}, look_alikes {frozenset({a, b}): shared features of 16})."""
    meanings = {v["gloss"]: list(v["english"]) for v in VOCAB}
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        logging.warning("asl2english/lexicon.json missing or unreadable; run python -m asl2english.build_lexicon")
        return meanings, {}
    for gloss, entry in data.get("signs", {}).items():
        if gloss in meanings:
            meanings[gloss] += [t for t in entry.get("translations", []) if t not in meanings[gloss]]
    pairs = {frozenset((a, b)): int(n) for a, b, n in data.get("look_alikes", []) if a in meanings and b in meanings}
    return meanings, pairs


MEANINGS, LOOK_ALIKES = load()
