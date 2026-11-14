"""Load cached landmark clips and augment them. Shared by train.py, evaluate.py and reference.py.

Expected data layout (anything that follows it trains, whatever the source):
  ml/data/landmarks/<GLOSS>/<clip>.npy   float (T, 21, 3) raw MediaPipe hand landmarks, one hand,
                                         NaN rows (or all-zero rows) for frames with no hand
  ml/data/landmarks/splits.csv           optional: path,gloss,split,signer[,...]
Folders named after a gloss in shared/vocab.json are that sign; any other folder is "not a vocab sign".
Without splits.csv, clips are split by signer (filename prefix before "__", e.g. "evan__milk1.npy"),
or by file if there is no prefix, using a stable hash (70/15/15).
"""
import csv
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

import recognizer as R

ML = Path(__file__).parent
LANDMARKS = ML / "data" / "landmarks"
VOCAB = ML.parent / "shared" / "vocab.json"


def vocab_glosses():
    return [v["gloss"] for v in json.loads(VOCAB.read_text())]


@dataclass
class Clip:
    path: str
    gloss: str              # folder name
    label: str              # vocab gloss or R.OTHER
    split: str
    signer: str = ""
    source_gloss: str = ""
    seq: np.ndarray = field(default=None, repr=False)


def _hash_split(key):
    h = int(hashlib.md5(key.encode()).hexdigest(), 16) % 100
    return "train" if h < 70 else "val" if h < 85 else "test"


def load_clips(root=LANDMARKS, include_other=True):
    vocab = set(vocab_glosses())
    meta = {}
    split_file = Path(root) / "splits.csv"
    if split_file.exists():
        with open(split_file, newline="", encoding="utf8") as f:
            meta = {r["path"]: r for r in csv.DictReader(f)}
    clips = []
    for p in sorted(Path(root).glob("*/*.npy")):
        rel = f"{p.parent.name}/{p.name}"
        gloss = p.parent.name
        label = gloss if gloss in vocab else R.OTHER
        if label == R.OTHER and not include_other:
            continue
        m = meta.get(rel, {})
        signer = m.get("signer") or (p.stem.split("__")[0] if "__" in p.stem else "")
        split = m.get("split") or _hash_split(signer or rel)
        seq = np.load(p).astype(np.float64)
        seq[(seq == 0).all(axis=(1, 2))] = np.nan
        clips.append(Clip(rel, gloss, label, split, signer, m.get("source_gloss", gloss), seq))
    return clips


def augment(seq, rng):
    """Random temporal crop, time warp, frame dropout, mirror, rotation, aspect change and jitter on raw landmarks."""
    s = seq.copy()
    valid = np.flatnonzero(~np.isnan(s[:, 0, 0]))
    if len(valid) < R.MIN_FRAMES:
        return s
    s = s[valid[0]:valid[-1] + 1]
    T = len(s)
    if rng.random() < 0.5 and T > 8:                       # temporal crop (shorter browser windows)
        n = max(R.MIN_FRAMES + 2, int(T * rng.uniform(0.6, 1.0)))
        a = rng.integers(0, T - n + 1)
        s = s[a:a + n]
        T = n
    if rng.random() < 0.5:                                 # non-uniform speed
        g = np.exp(rng.normal(0, 0.2))
        idx = np.round((np.linspace(0, 1, T) ** g) * (T - 1)).astype(int)
        s = s[idx]
    if rng.random() < 0.5:                                 # frame dropout
        drop = rng.random(T) < rng.uniform(0, 0.3)
        s[drop] = np.nan
    ok = ~np.isnan(s[:, 0, 0])
    if ok.sum() < R.MIN_FRAMES:
        return seq.copy()
    c = np.nanmean(s[ok][:, :, :2].reshape(-1, 2), axis=0)
    xy = s[:, :, :2] - c
    if rng.random() < 0.5:                                 # mirror: same sign made with the other hand
        xy[..., 0] = -xy[..., 0]
    a = rng.normal(0, np.deg2rad(10))
    rot = np.array([[np.cos(a), -np.sin(a)], [np.sin(a), np.cos(a)]])
    xy = xy @ rot.T
    xy[..., 0] *= rng.uniform(0.85, 1.15)                  # camera aspect ratio / scaling
    xy *= rng.uniform(0.8, 1.25)
    s[:, :, :2] = xy + c
    size = np.nanmedian(np.linalg.norm(s[:, 9] - s[:, 0], axis=-1))
    s += rng.normal(0, 0.02 * size, s.shape)               # landmark jitter, 2% of hand size
    s[:, :, 2] *= rng.uniform(0.8, 1.2)
    return s


def features(seq, length=R.SEQ_LEN):
    return R.sequence_features(seq, length)


def browser_window(seq, n=15, where="middle"):
    """A window like the one the browser sends: n consecutive frames from the detected span."""
    valid = np.flatnonzero(~np.isnan(seq[:, 0, 0]))
    if not len(valid):
        return seq
    s = seq[valid[0]:valid[-1] + 1]
    if len(s) <= n:
        return s
    a = (len(s) - n) // 2 if where == "middle" else len(s) - n
    return s[a:a + n]
