"""Tests for reference.lookup(). Run: python ml/test_reference.py (or pytest ml/test_reference.py)."""
import json
from pathlib import Path

import numpy as np

import recognizer as R
from reference import REFERENCES, lookup

VOCAB = json.loads((Path(__file__).parent.parent / "shared" / "vocab.json").read_text())


def test_unknown_words_return_none():
    for w in ("banana", "", "   ", None, 42, "milkshake"):
        assert lookup(w) is None, w


def test_every_english_word_maps_to_its_gloss():
    if not REFERENCES.exists():
        return
    for v in VOCAB:
        for w in v["english"] + [v["gloss"], v["gloss"].lower()]:
            r = lookup(w.upper() if w == v["english"][0] else w)
            assert r is not None and r["gloss"] == v["gloss"], (w, r and r["gloss"])


def test_reference_shape_and_values():
    if not REFERENCES.exists():
        return
    r = lookup("thirsty")
    assert r["gloss"] == "WATER" and "thirsty" in r["english"]
    f = np.asarray(r["frames"])
    assert f.ndim == 3 and f.shape[1:] == (21, 3) and len(f) >= R.MIN_FRAMES
    assert np.isfinite(f).all()
    assert r["fps"] > 0 and r["source"] in ("ASL Citizen", "WLASL") and r["n_candidates"] >= 1


def test_references_are_recognised_as_their_own_sign():
    """Each reference is a real training clip, so the recogniser should read it back (sanity, not accuracy)."""
    if not REFERENCES.exists() or R.load_model() is None:
        return
    hits = sum(R.predict(lookup(v["gloss"])["frames"])["sign"] == v["gloss"] for v in VOCAB)
    assert hits >= len(VOCAB) - 2, f"only {hits}/{len(VOCAB)} references recognised"


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("reference tests passed")
