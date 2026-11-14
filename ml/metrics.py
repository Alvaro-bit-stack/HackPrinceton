"""Closed-set accuracy and open-set precision / coverage at a confidence threshold."""
import numpy as np

import recognizer as R


NEG_RATIO = 1.0   # in precision, all non-vocab clips together weigh as much as NEG_RATIO x all vocab clips


def summarize(true, pred, conf, other, tau, neg_ratio=NEG_RATIO):
    """true: labels (vocab gloss or R.OTHER). pred: best vocab gloss. conf: its confidence.
    other: model says "not a vocab sign". A prediction is accepted if not other and conf >= tau.
    Precision counts wrong answers on non-vocab clips, re-weighted so they make up `neg_ratio` times the
    vocab clips (the data has ~5x more non-vocab clips than a child practising vocab signs would produce).
    `precision_unweighted` is the raw ratio."""
    true, pred = np.asarray(true, dtype=object), np.asarray(pred, dtype=object)
    conf, other = np.asarray(conf, float), np.asarray(other, bool)
    pos = true != R.OTHER
    accepted = ~other & (conf >= tau)
    correct = accepted & (pred == true)
    n_acc = int(accepted.sum())
    w = np.where(pos, 1.0, neg_ratio * pos.sum() / max(1, (~pos).sum()))
    w_acc = float((w * accepted).sum())
    return {
        "threshold": float(tau),
        "n_sign_clips": int(pos.sum()),
        "n_other_clips": int((~pos).sum()),
        "closed_set_accuracy": float((pred[pos] == true[pos]).mean()) if pos.any() else float("nan"),
        "accepted": n_acc,
        "precision": float((w * correct).sum() / w_acc) if w_acc else float("nan"),
        "precision_unweighted": float(correct.sum() / n_acc) if n_acc else float("nan"),
        "precision_vocab_only": float(correct[pos].sum() / accepted[pos].sum()) if accepted[pos].any() else float("nan"),
        "coverage": float(accepted[pos].mean()) if pos.any() else float("nan"),
        "accepted_correct_rate": float(correct[pos].mean()) if pos.any() else float("nan"),
        "false_accept_rate_other": float(accepted[~pos].mean()) if (~pos).any() else float("nan"),
        "wrong_sign_rate": float((accepted[pos] & (pred[pos] != true[pos])).mean()) if pos.any() else float("nan"),
    }


def choose_threshold(true, pred, conf, other, target=0.90, min_accepted=5):
    """Smallest threshold such that precision >= target at it and at every higher threshold
    (with at least `min_accepted` accepted predictions). Returns (tau, met_target)."""
    grid = np.round(np.arange(0.0, 1.0001, 0.01), 2)
    ok = []
    for t in grid:
        s = summarize(true, pred, conf, other, t)
        ok.append(s["accepted"] < min_accepted or s["precision"] >= target)
    ok = np.array(ok)
    for i, t in enumerate(grid):
        if ok[i:].all() and summarize(true, pred, conf, other, t)["accepted"] >= min_accepted:
            return float(t), True
    best = max(grid, key=lambda t: (summarize(true, pred, conf, other, t)["precision"] or 0))
    return float(best), False


def tradeoff(true, pred, conf, other, taus=(0.0, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95)):
    return [summarize(true, pred, conf, other, t) for t in taus]


def per_sign(true, pred, conf, other, tau, glosses):
    true, pred = np.asarray(true, dtype=object), np.asarray(pred, dtype=object)
    conf, other = np.asarray(conf, float), np.asarray(other, bool)
    accepted = ~other & (conf >= tau)
    rows = []
    for g in glosses:
        m = true == g
        said = accepted & (pred == g)
        rows.append({
            "sign": g,
            "n": int(m.sum()),
            "accuracy": float((pred[m] == g).mean()) if m.any() else float("nan"),
            "precision": float((true[said] == g).mean()) if said.any() else float("nan"),
            "n_predicted": int(said.sum()),
            "coverage": float(accepted[m].mean()) if m.any() else float("nan"),
            "accepted_correct": float((accepted[m] & (pred[m] == g)).mean()) if m.any() else float("nan"),
        })
    return rows


def confusions(true, pred, top=10):
    pairs = {}
    for t, p in zip(true, pred):
        if t != R.OTHER and p != t:
            pairs[(t, p)] = pairs.get((t, p), 0) + 1
    return sorted(pairs.items(), key=lambda kv: -kv[1])[:top]
