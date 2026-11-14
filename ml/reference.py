"""English word -> reference landmark sequence for that sign (retrieval only; nothing is generated).

    from ml.reference import lookup
    lookup("thirsty")   # {"gloss": "WATER", "english": [...], "frames": [[[x, y, z] x21] x T], "fps": 30.0, ...}
    lookup("banana")    # None

The reference for each sign is the medoid training clip: the real recording whose sequence features are
closest on average to every other training clip of that sign. They are precomputed into
ml/references.npz (small, committed) by `python ml/reference.py --build`, so lookup() needs no dataset.
"""
import json
from pathlib import Path

import numpy as np

ML = Path(__file__).parent
REFERENCES = ML / "references.npz"
VOCAB = ML.parent / "shared" / "vocab.json"

_cache = {}


def _vocab():
    if "vocab" not in _cache:
        _cache["vocab"] = json.loads(VOCAB.read_text())
    return _cache["vocab"]


def gloss_for(word):
    """'Thirsty' -> 'WATER'; also accepts the gloss itself ('ALL-DONE'). None if unknown."""
    if not isinstance(word, str) or not word.strip():
        return None
    w = word.strip().lower()
    for v in _vocab():
        if w == v["gloss"].lower() or w in (e.lower() for e in v["english"]):
            return v["gloss"]
    return None


def _load():
    if "refs" not in _cache:
        if not REFERENCES.exists():
            _cache["refs"] = None
        else:
            z = np.load(REFERENCES, allow_pickle=False)
            _cache["refs"] = {k: z[k] for k in z.files}
    return _cache["refs"]


def lookup(word):
    """Returns {"gloss", "english", "frames" (T x 21 x 3 list), "fps", "source", "clip", "n_candidates"},
    or None if the word isn't in the vocab (or no reference was built for it)."""
    gloss = gloss_for(word)
    refs = _load()
    if gloss is None or refs is None:
        return None
    glosses = [str(g) for g in refs["glosses"]]
    if gloss not in glosses:
        return None
    i = glosses.index(gloss)
    n = int(refs["lengths"][i])
    english = next(v["english"] for v in _vocab() if v["gloss"] == gloss)
    return {"gloss": gloss, "english": list(english), "frames": refs["frames"][i, :n].tolist(),
            "fps": float(refs["fps"][i]), "source": str(refs["sources"][i]), "clip": str(refs["clips"][i]),
            "n_candidates": int(refs["n_candidates"][i])}


def _fill_gaps(seq):
    """Trim to the detected span and linearly interpolate frames where the hand was missed."""
    valid = np.flatnonzero(~np.isnan(seq[:, 0, 0]))
    s = seq[valid[0]:valid[-1] + 1]
    v = valid - valid[0]
    t = np.arange(len(s))
    flat = s.reshape(len(s), -1)
    out = np.stack([np.interp(t, v, flat[v, j]) for j in range(flat.shape[1])], axis=1)
    return out.reshape(len(s), 21, 3)


def build():
    import dataset as D
    import recognizer as R
    clips = [c for c in D.load_clips(include_other=False) if c.split == "train"]
    picks = []
    for gloss in D.vocab_glosses():
        cands = [c for c in clips if c.label == gloss]
        if not cands:
            continue
        feats = np.stack([R.sequence_features(c.seq)[:, :66].ravel() for c in cands])
        feats = (feats - feats.mean(0)) / (feats.std(0) + 1e-6)
        d = np.linalg.norm(feats[:, None] - feats[None], axis=-1).mean(1)
        best = cands[int(np.argmin(d))]
        source = "WLASL" if best.path.split("/")[1].startswith("wlasl") else "ASL Citizen"
        picks.append((gloss, _fill_gaps(best.seq), 25.0 if source == "WLASL" else 30.0, source, best.path, len(cands)))
    L = max(len(p[1]) for p in picks)
    frames = np.zeros((len(picks), L, 21, 3), np.float32)
    for i, p in enumerate(picks):
        frames[i, :len(p[1])] = p[1]
    np.savez_compressed(REFERENCES, glosses=np.array([p[0] for p in picks]), frames=frames,
                        lengths=np.array([len(p[1]) for p in picks]), fps=np.array([p[2] for p in picks]),
                        sources=np.array([p[3] for p in picks]), clips=np.array([p[4] for p in picks]),
                        n_candidates=np.array([p[5] for p in picks]))
    _cache.clear()
    print(f"wrote {REFERENCES} ({REFERENCES.stat().st_size / 1024:.0f} KB): " +
          ", ".join(f"{p[0]}<-{p[4]}" for p in picks))


if __name__ == "__main__":
    import sys
    if "--build" in sys.argv:
        build()
    else:
        for w in ("milk", "Thirsty", "all-done", "banana"):
            r = lookup(w)
            print(w, "->", None if r is None else (r["gloss"], len(r["frames"]), r["source"], r["clip"]))
