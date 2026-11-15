"""Continuous clip of hand landmarks -> ordered list of separate signs, each with ranked guesses.

Wraps ml/recognizer.py without changing it: predict() there still answers POST /recognize with one sign per clip.
Here a clip is first cut where the hand leaves the frame, then any long stretch is scanned with a sliding window
so two signs made without dropping the hands are still separated. Each piece is scored by the trained model
(ml/model.npz) and returns its top glosses, limited to shared/vocab.json.

If model.npz is missing, a clearly marked stand-in (nearest template on the last frame, ml/templates.json) is
used so the rest of the pipeline can still be built and tested; its answers are much weaker.
"""
import numpy as np

from backend.translate import GLOSSES
from ml import recognizer as R

MAX_FRAMES = 900        # about 30 s at 30 fps
GAP_FRAMES = 4          # this many hand-less frames in a row = the child dropped their hands between signs
WINDOW = 30             # sliding window, in frames (about one sign at 30 fps)
STRIDE = 5
LONG_RUN = 45           # a run of hand frames longer than this may hold more than one sign
FLOOR = 0.25            # below this the piece is treated as "no sign" (movement between signs, fidgeting)
TOP_K = 3
MODEL = "model"
STAND_IN = "stand-in: template match on the last frame (no trained model found)"


def validate_frames(frames):
    """Raises ValueError for input the recognizer should never see. A frame is 21 (x, y, z) points,
    or null / [] when no hand was seen (those gaps help split signs)."""
    if not isinstance(frames, list) or not frames:
        raise ValueError("frames must be a non-empty list")
    if len(frames) > MAX_FRAMES:
        raise ValueError(f"frames must have at most {MAX_FRAMES} entries")
    for i, f in enumerate(frames):
        if f is None or (isinstance(f, list) and not f):
            continue
        try:
            a = np.asarray(f, dtype=float)
        except (ValueError, TypeError):
            raise ValueError(f"frame {i} must be 21 points of 3 numbers") from None
        if a.shape != (21, 3):
            raise ValueError(f"frame {i} must be 21 points of 3 numbers")
        if not np.isfinite(a).all():
            raise ValueError(f"frame {i} has a number that is not finite")


def _to_seq(frames):
    """(T, 21, 3) with NaN rows where no hand was seen. The hand-track cleanup (keep_one_hand) runs per piece
    inside sequence_features: over a whole clip, the jump between two signs would look like a second hand."""
    seq = np.full((len(frames), 21, 3), np.nan)
    for i, f in enumerate(frames):
        if f is not None and len(f):
            seq[i] = np.asarray(f, dtype=float)
    return seq


def hand_runs(seq, gap=GAP_FRAMES):
    """[(start, end)] of stretches with a hand, split where it is missing for `gap` frames or more (end exclusive)."""
    present = np.flatnonzero(~np.isnan(seq[:, 0, 0]))
    if not len(present):
        return []
    runs, start = [], present[0]
    for a, b in zip(present, present[1:]):
        if b - a > gap:
            runs.append((int(start), int(a) + 1))
            start = b
    runs.append((int(start), int(present[-1]) + 1))
    return runs


def _ranked_model(m, seq):
    """Top glosses for one piece, or [] if it is too short or looks like no sign."""
    x = R.sequence_features(seq, int(m["seq_len"]))
    if x is None:
        return []
    p = R.model_probs(m, x)
    classes = [str(c) for c in m["classes"]]
    ranked = sorted(((float(p[i]), c) for i, c in enumerate(classes) if c in GLOSSES), reverse=True)
    if not ranked or ranked[0][0] < FLOOR:
        return []
    return [{"gloss": c, "confidence": round(q, 3)} for q, c in ranked[:TOP_K]]


def _ranked_templates(templates, seq):
    valid = np.flatnonzero(~np.isnan(seq[:, 0, 0]))
    if len(valid) < R.MIN_FRAMES or not templates:
        return []
    x = R.normalize(seq[valid[-1]])
    scored = []
    for gloss, examples in templates.items():
        if gloss in GLOSSES:
            d = float(np.linalg.norm(np.asarray(examples, dtype=float).reshape(-1, 63) - x, axis=1).min())
            scored.append((1.0 / (1.0 + d), gloss))
    scored.sort(reverse=True)
    if not scored or scored[0][0] < FLOOR:
        return []
    return [{"gloss": g, "confidence": round(q, 3)} for q, g in scored[:TOP_K]]


def _split_long_run(m, seq, start, end):
    """Sliding window over one long run: windows whose best guess agrees form one sign; boundaries go
    halfway between neighbouring groups. Returns [(start, end)]."""
    labels = []
    for s in range(start, max(start + 1, end - WINDOW + 1), STRIDE):
        top = _ranked_model(m, seq[s:s + WINDOW])
        ok = top and top[0]["confidence"] >= float(m["min_confidence"])
        labels.append((s, top[0]["gloss"] if ok else None))
    groups = []  # [gloss, first window start, last window start]
    for s, g in labels:
        if g is None:
            continue
        if groups and groups[-1][0] == g and s - groups[-1][2] <= 2 * STRIDE:
            groups[-1][2] = s
        else:
            groups.append([g, s, s])
    if len(groups) < 2:
        return [(start, end)]
    cuts = [start]
    for a, b in zip(groups, groups[1:]):
        cuts.append((a[2] + WINDOW // 2 + b[1] + WINDOW // 2) // 2)
    cuts.append(end)
    return list(zip(cuts, cuts[1:]))


def recognize_signs(frames, model="default"):
    """frames -> {"recognizer": str, "signs": [{"start", "end", "glosses": [{"gloss", "confidence"}, ...]}]}.
    Signs are in the order they were made; glosses are best first. Never raises on validated input.
    `model`: "default" loads ml/model.npz; None forces the stand-in (used by tests)."""
    m = R.load_model() if model == "default" else model
    seq = _to_seq(frames)
    if m is None:
        templates = R.load_templates()
        signs = []
        for s, e in hand_runs(seq):
            top = _ranked_templates(templates, seq[s:e])
            if top:
                signs.append({"start": s, "end": e, "glosses": top})
        return {"recognizer": STAND_IN, "signs": signs}
    signs = []
    for s, e in hand_runs(seq):
        pieces = _split_long_run(m, seq, s, e) if e - s > LONG_RUN else [(s, e)]
        for ps, pe in pieces:
            top = _ranked_model(m, seq[ps:pe])
            if not top:
                continue
            if signs and signs[-1]["glosses"][0]["gloss"] == top[0]["gloss"] and signs[-1]["end"] == ps:
                signs[-1]["end"] = pe  # the window split one sign in two: join it back
                continue
            signs.append({"start": ps, "end": pe, "glosses": top})
    return {"recognizer": MODEL, "signs": signs}
