"""Sign recognition: hand landmarks in, sign label and confidence out.

Owner: Person 1. The backend only ever calls predict(), so everything else here can change freely.
Run `python ml/recognizer.py` for the self-check.

predict() uses the sequence model in model.npz (a small 1D-CNN over the whole frame sequence,
trained by ml/train.py, run here in pure numpy so the backend needs no torch). If model.npz is
missing, or the caller passes `templates`, it falls back to the original last-frame
nearest-neighbour on templates.json.
"""
import json
from pathlib import Path

import numpy as np

TEMPLATES = Path(__file__).parent / "templates.json"  # {"MILK": [[63 numbers], ...], ...}
MODEL = Path(__file__).parent / "model.npz"
MIN_CONFIDENCE = 0.6        # template fallback only; the model's threshold is stored in model.npz
SEQ_LEN = 32                # frames after resampling
MIN_FRAMES = 4              # fewer valid frames than this -> no guess
OTHER = "_OTHER"            # model class for "not one of the vocab signs"
NONE = {"sign": None, "confidence": 0.0}


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


# ---------------------------------------------------------------- preprocessing (shared with train.py)

def to_array(frames):
    """Any list of frames -> float (T, 21, 3) with NaN rows for frames that are malformed or non-finite."""
    if frames is None:
        return np.zeros((0, 21, 3))
    try:
        arr = np.asarray(frames, dtype=float)
        if arr.ndim == 3 and arr.shape[1:] == (21, 3):
            out = arr.copy()
        elif arr.ndim == 2 and arr.shape[1] == 63:
            out = arr.reshape(-1, 21, 3).copy()
        else:
            raise ValueError
    except (ValueError, TypeError):                # ragged input: check frame by frame
        out = np.full((len(frames), 21, 3), np.nan)
        for i, f in enumerate(frames):
            try:
                out[i] = np.asarray(f, dtype=float).reshape(21, 3)
            except (ValueError, TypeError):
                pass
    out[~np.isfinite(out).all(axis=(1, 2))] = np.nan
    return out


def keep_one_hand(seq, jump=1.5):
    """The browser sends the first detected hand each frame, which can flip between hands.
    Split frames into two tracks by wrist continuity and keep the longer one (others -> NaN)."""
    valid = np.flatnonzero(~np.isnan(seq[:, 0, 0]))
    if len(valid) < 3:
        return seq
    size = np.median(np.linalg.norm(seq[valid, 9, :2] - seq[valid, 0, :2], axis=-1)) or 1e-3
    last, track = [None, None], np.full(len(seq), -1)
    for i in valid:
        w = seq[i, 0, :2]
        d = [np.inf if l is None else np.linalg.norm(w - l) / size for l in last]
        if last[0] is None:
            k = 0
        elif min(d) > jump and last[1] is None:
            k = 1                                  # big jump: start the second track
        else:
            k = int(np.argmin(d))
        track[i], last[k] = k, w
    keep = np.argmax([(track == 0).sum(), (track == 1).sum()])
    out = seq.copy()
    out[(track != keep) & (track >= 0)] = np.nan
    return out


def frame_features(seq):
    """(T, 21, 3) raw landmarks without NaN rows -> (T, 66): normalize() per frame (63), plus the wrist's
    path and the hand's apparent size relative to the clip, so movement survives normalisation (3)."""
    shape = np.stack([normalize(f) for f in seq])
    size = np.linalg.norm(seq[:, 9] - seq[:, 0], axis=-1)
    ref = np.median(size) or 1e-3
    path = (seq[:, 0, :2] - seq[:, 0, :2].mean(0)) / ref
    depth = np.log(np.maximum(size, 1e-6) / ref)[:, None]
    return np.concatenate([shape, path, depth], axis=1)


def sequence_features(frames, length=SEQ_LEN):
    """Frames -> (length, 132) model input, or None if there are fewer than MIN_FRAMES usable frames.
    Missing frames are interpolated; the span from first to last detected frame is resampled to `length`."""
    seq = keep_one_hand(to_array(frames))
    valid = np.flatnonzero(~np.isnan(seq[:, 0, 0]))
    if len(valid) < MIN_FRAMES:
        return None
    f = frame_features(seq[valid])
    t = np.linspace(valid[0], valid[-1], length)
    x = np.stack([np.interp(t, valid, f[:, j]) for j in range(f.shape[1])], axis=1)
    vel = np.diff(x, axis=0, prepend=x[:1])
    return np.concatenate([x, vel], axis=1).astype(np.float32)


# ---------------------------------------------------------------- numpy inference for the trained model

_model_cache = {}


def load_model(path=MODEL):
    path = Path(path)
    if not path.exists():
        return None
    key = (str(path), path.stat().st_mtime)
    if key not in _model_cache:
        z = np.load(path, allow_pickle=False)
        _model_cache.clear()
        _model_cache[key] = {k: z[k] for k in z.files}
    return _model_cache[key]


def _conv1d(x, w, b, dilation):
    """x (T, Cin), w (Cout, Cin, K) 'same' padding -> (T, Cout)."""
    k = w.shape[2]
    pad = dilation * (k // 2)
    xp = np.pad(x, ((pad, pad), (0, 0)))
    T = x.shape[0]
    cols = np.stack([xp[i * dilation:i * dilation + T] for i in range(k)], axis=2)   # (T, Cin, K)
    return np.tensordot(cols, w, axes=([1, 2], [1, 2])) + b


def model_logits(m, x):
    """x (SEQ_LEN, 132) -> logits, mirroring train.SignCNN in eval mode (batch-norm folded into conv)."""
    h = (x - m["mean"]) / m["std"]
    for i in range(int(m["n_layers"])):
        h = np.maximum(_conv1d(h, m[f"w{i}"], m[f"b{i}"], int(m["dilations"][i])), 0.0)
    pooled = np.concatenate([h.mean(0), h.max(0)])
    return pooled @ m["fc_w"].T + m["fc_b"]


def model_probs(m, x):
    z = model_logits(m, x) / float(m["temperature"])
    z = np.exp(z - z.max())
    return z / z.sum()


def _predict_model(frames, m):
    x = sequence_features(frames, int(m["seq_len"]))
    if x is None:
        return dict(NONE)
    p = model_probs(m, x)
    classes = [str(c) for c in m["classes"]]
    best = int(np.argmax(p))
    if classes[best] == OTHER:
        return {"sign": None, "confidence": 0.0}
    conf = float(p[best])
    return {"sign": classes[best] if conf >= float(m["min_confidence"]) else None, "confidence": round(conf, 3)}


def _predict_templates(frames, templates):
    """Original baseline: nearest-neighbour on the last usable frame only (reads handshape, ignores movement)."""
    if not templates:
        return dict(NONE)
    seq = to_array(frames)
    valid = np.flatnonzero(~np.isnan(seq[:, 0, 0]))
    if not len(valid):
        return dict(NONE)
    x = normalize(seq[valid[-1]])
    best, dist = None, float("inf")
    for gloss, examples in templates.items():
        d = float(np.linalg.norm(np.asarray(examples, dtype=float).reshape(-1, 63) - x, axis=1).min())
        if d < dist:
            best, dist = gloss, d
    confidence = 1.0 / (1.0 + dist)
    return {"sign": best if confidence >= MIN_CONFIDENCE else None, "confidence": round(confidence, 3)}


def predict(frames, templates=None):
    """frames: list of frames, each 21 (x, y, z) points. Returns {"sign": str | None, "confidence": float}.
    Never raises on bad input; returns {"sign": None, "confidence": 0.0} instead."""
    try:
        if frames is None or len(frames) == 0:
            return dict(NONE)
        if templates is not None:
            return _predict_templates(frames, templates)
        m = load_model()
        if m is not None:
            return _predict_model(frames, m)
        return _predict_templates(frames, load_templates())
    except Exception:
        return dict(NONE)


# ---------------------------------------------------------------- self-check

def _synthetic_hand(rng):
    return rng.random((21, 3))


def _check_template_baseline(rng):
    a, b = _synthetic_hand(rng), _synthetic_hand(rng)
    t = {"A": np.array([normalize(a)]), "B": np.array([normalize(b)])}
    moved = a * 2.5 + 7                            # same handshape, bigger and somewhere else
    assert predict([moved], t)["sign"] == "A"
    assert predict([b + rng.normal(0, .005, b.shape)], t)["sign"] == "B"
    assert predict([], t) == {"sign": None, "confidence": 0.0}


def _check_edge_cases():
    hand = np.random.default_rng(1).random((21, 3))
    bad_inputs = [None, [], [[]], [hand[:5]], [[1, 2, 3]], "not frames", [hand * np.nan] * 10,
                  [hand] * 2, [np.full((21, 3), np.inf)] * 8, [[["a", "b", "c"]] * 21] * 8, 42]
    for bad in bad_inputs:
        r = predict(bad)
        assert set(r) == {"sign", "confidence"}, (bad, r)
        assert r["sign"] is None and r["confidence"] == 0.0, (type(bad), r)
    # NaNs or junk in some frames must not crash and must not stop a prediction
    frames = [hand + i * 0.01 for i in range(12)]
    frames[3] = hand * np.nan
    frames[5] = [[0, 0]] * 3
    r = predict(frames)
    assert set(r) == {"sign", "confidence"} and isinstance(r["confidence"], float)


def _movement_pair(rng, n=8, frames=24):
    """Two synthetic signs with the SAME handshape that differ only in movement: the hand travels
    left->right and ends on the right ("A"), or right->left and ends on the left... with the same
    final frame for both, so the last frame is identical and only the motion tells them apart."""
    base = rng.random((21, 3)) * 0.1
    out = {"A": [], "B": []}
    for _ in range(n):
        shape = base + rng.normal(0, 0.002, base.shape)
        t = np.linspace(0, 1, frames)
        for label, path in (("A", np.stack([t, 0 * t], 1)), ("B", np.stack([0 * t, t], 1))):
            # both end at the same place (0.5, 0.5); A arrives horizontally, B vertically
            xy = 0.5 + 0.3 * (path - path[-1])
            seq = np.repeat(shape[None], frames, 0)
            seq[:, :, :2] += xy[:, None, :]
            out[label].append(seq + rng.normal(0, 0.0005, seq.shape))
    return out


def _check_movement_only():
    """The last-frame baseline cannot separate signs that differ only by movement; a sequence model can.
    Uses a nearest-centroid classifier on sequence_features() as a stand-in for the trained model so the
    check does not depend on model.npz, then (if present) checks the real model returns a valid answer."""
    rng = np.random.default_rng(3)
    train, test = _movement_pair(rng), _movement_pair(rng, n=4)
    templates = {g: np.array([normalize(s[-1]) for s in seqs]) for g, seqs in train.items()}
    centroids = {g: np.mean([sequence_features(s) for s in seqs], 0) for g, seqs in train.items()}
    base_ok = seq_ok = total = 0
    for g, seqs in test.items():
        for s in seqs:
            total += 1
            base_ok += _predict_templates(list(s), templates)["sign"] == g
            x = sequence_features(list(s))
            seq_ok += min(centroids, key=lambda c: np.linalg.norm(centroids[c] - x)) == g
    assert base_ok <= total * 0.75, f"baseline unexpectedly separated movement-only signs ({base_ok}/{total})"
    assert seq_ok == total, f"sequence features failed movement-only signs ({seq_ok}/{total})"
    return base_ok, seq_ok, total


def _check_model():
    m = load_model()
    if m is None:
        return "model.npz not found: predict() uses the template fallback"
    classes = [str(c) for c in m["classes"]]
    x = np.random.default_rng(4).normal(size=(int(m["seq_len"]), int(m["mean"].shape[-1]))).astype(np.float32)
    p = model_probs(m, x)
    assert p.shape == (len(classes),) and abs(p.sum() - 1) < 1e-5
    ref = Path(__file__).parent / "model_selfcheck.npz"
    if ref.exists():                                # recorded clips with known labels, saved by train.py
        z = np.load(ref, allow_pickle=False)
        hits = 0
        for i in range(len(z["labels"])):
            n = int(z["lengths"][i])
            r = predict(list(z["frames"][i][:n]))
            hits += r["sign"] == str(z["labels"][i])
            assert set(r) == {"sign", "confidence"}
        assert hits >= 0.8 * len(z["labels"]), f"model got {hits}/{len(z['labels'])} reference clips"
        return f"model.npz loaded ({len(classes) - 1} signs); reference clips {hits}/{len(z['labels'])} correct"
    return f"model.npz loaded ({len(classes) - 1} signs)"


if __name__ == "__main__":
    _check_template_baseline(np.random.default_rng(0))
    _check_edge_cases()
    b, s, n = _check_movement_only()
    print(f"movement-only pair: last-frame baseline {b}/{n}, sequence features {s}/{n}")
    print(_check_model())
    print("recognizer self-check passed")
