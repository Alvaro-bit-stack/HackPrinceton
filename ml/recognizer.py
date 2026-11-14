"""Sign recognition: hand landmarks in, sign label and confidence out.

Owner: Person 1. The backend only ever calls predict(), so everything else here can change freely.
Run `python ml/recognizer.py` for the self-check.
"""
import json
from pathlib import Path

import numpy as np

TEMPLATES = Path(__file__).parent / "templates.json"  # {"MILK": [[63 numbers], ...], ...}
MIN_CONFIDENCE = 0.6


def normalize(hand):
    """21 (x, y, z) points -> 63 numbers that ignore where the hand is and how big it is."""
    p = np.asarray(hand, dtype=float).reshape(21, 3)
    p = p - p[0]                                   # wrist at the origin
    scale = np.linalg.norm(p[9]) or 1.0            # wrist to middle knuckle
    return (p / scale).ravel()


def load_templates(path=TEMPLATES):
    if not path.exists():
        return {}
    return {g: np.asarray(v, dtype=float) for g, v in json.loads(path.read_text()).items()}


def add_template(gloss, hand, path=TEMPLATES):
    """Record one example of a sign. Call it a few times per sign, with different people."""
    data = json.loads(path.read_text()) if path.exists() else {}
    data.setdefault(gloss, []).append(normalize(hand).tolist())
    path.write_text(json.dumps(data))


def predict(frames, templates=None):
    """frames: list of frames, each 21 (x, y, z) points. Returns {"sign": str | None, "confidence": float}."""
    # ponytail: nearest-neighbour on the last frame only, so it reads handshape and ignores movement.
    # Upgrade to a sequence model (or DTW over all frames) once signs that differ by motion are added.
    templates = load_templates() if templates is None else templates
    if not frames or not templates:
        return {"sign": None, "confidence": 0.0}
    x = normalize(frames[-1])
    best, dist = None, float("inf")
    for gloss, examples in templates.items():
        d = float(np.linalg.norm(examples - x, axis=1).min())
        if d < dist:
            best, dist = gloss, d
    confidence = 1.0 / (1.0 + dist)
    return {"sign": best if confidence >= MIN_CONFIDENCE else None, "confidence": round(confidence, 3)}


if __name__ == "__main__":
    rng = np.random.default_rng(0)
    a, b = rng.random((21, 3)), rng.random((21, 3))
    t = {"A": np.array([normalize(a)]), "B": np.array([normalize(b)])}
    moved = a * 2.5 + 7                            # same handshape, bigger and somewhere else
    assert predict([moved], t)["sign"] == "A"
    assert predict([b + rng.normal(0, .005, b.shape)], t)["sign"] == "B"
    assert predict([], t) == {"sign": None, "confidence": 0.0}
    print("recognizer self-check passed")
