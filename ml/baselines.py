"""Baselines, so the sequence model's improvement can be measured.

A: the original recognizer: nearest neighbour on the last frame's normalize() vector.
B: nearest neighbour on whole sequences: k-NN on resampled sequence features, and 1-NN DTW.
Every scorer returns, per clip, (predicted vocab gloss, confidence, predicted_other: bool).
"""
import numpy as np

import recognizer as R


def _last_frame(seq):
    valid = np.flatnonzero(~np.isnan(seq[:, 0, 0]))
    return R.normalize(seq[valid[-1]]) if len(valid) else None


class LastFrameNN:
    """Baseline A. Templates are the last frame of every training clip of a vocab sign."""
    name = "A: last-frame NN (original)"

    def fit(self, clips):
        self.X, self.y = [], []
        for c in clips:
            if c.label != R.OTHER and (v := _last_frame(c.seq)) is not None:
                self.X.append(v)
                self.y.append(c.label)
        self.X, self.y = np.array(self.X), np.array(self.y)
        return self

    def score(self, seq):
        x = _last_frame(seq)
        if x is None:
            return None, 0.0, True
        d = np.linalg.norm(self.X - x, axis=1)
        i = int(np.argmin(d))
        return self.y[i], 1.0 / (1.0 + float(d[i])), False


class SequenceKNN:
    """Baseline B1. k-NN (Euclidean) on standardised, flattened resampled sequences; includes _OTHER clips.
    Confidence = share of the k neighbours that vote for the winning vocab sign."""
    def __init__(self, k=5):
        self.k = k
        self.name = f"B1: sequence {k}-NN"

    def fit(self, clips):
        X, y = [], []
        for c in clips:
            f = R.sequence_features(c.seq)
            if f is not None:
                X.append(f[:, :66].ravel())
                y.append(c.label)
        X = np.array(X)
        self.mu, self.sd = X.mean(0), X.std(0) + 1e-6
        self.X, self.y = (X - self.mu) / self.sd, np.array(y)
        return self

    def score(self, seq):
        f = R.sequence_features(seq)
        if f is None:
            return None, 0.0, True
        x = (f[:, :66].ravel() - self.mu) / self.sd
        d = np.linalg.norm(self.X - x, axis=1)
        nn = self.y[np.argsort(d)[:self.k]]
        labels, counts = np.unique(nn, return_counts=True)
        best = labels[np.argmax(counts)]
        vocab_votes = {l: c for l, c in zip(labels, counts) if l != R.OTHER}
        top = max(vocab_votes, key=vocab_votes.get) if vocab_votes else None
        if top is None:                 # all neighbours are _OTHER: fall back to nearest vocab clip
            vi = np.flatnonzero(self.y != R.OTHER)
            top = self.y[vi[np.argmin(d[vi])]]
        return top, vocab_votes.get(top, 0) / self.k, best == R.OTHER


def dtw_many(a, B):
    """DTW distances between one (T, F) sequence and N templates (N, T, F), vectorised over templates."""
    cost = np.sqrt(((a[None, :, None, :] - B[:, None, :, :]) ** 2).sum(-1))     # (N, T, T)
    N, Ta, Tb = cost.shape
    D = np.full((N, Ta + 1, Tb + 1), np.inf)
    D[:, 0, 0] = 0
    for i in range(1, Ta + 1):
        for j in range(1, Tb + 1):
            D[:, i, j] = cost[:, i - 1, j - 1] + np.minimum(np.minimum(D[:, i - 1, j], D[:, i, j - 1]), D[:, i - 1, j - 1])
    return D[:, Ta, Tb] / (Ta + Tb)


class SequenceDTW:
    """Baseline B2. 1-NN with DTW on the per-frame features (16 resampled steps, to keep it fast)."""
    name = "B2: sequence 1-NN DTW"

    def __init__(self, length=16):
        self.length = length

    def fit(self, clips):
        X, y = [], []
        for c in clips:
            f = R.sequence_features(c.seq, self.length)
            if f is not None:
                X.append(f[:, :66])
                y.append(c.label)
        allf = np.concatenate(X)
        self.mu, self.sd = allf.mean(0), allf.std(0) + 1e-6
        self.X, self.y = np.stack([(x - self.mu) / self.sd for x in X]), np.array(y)
        return self

    def score(self, seq):
        f = R.sequence_features(seq, self.length)
        if f is None:
            return None, 0.0, True
        x = (f[:, :66] - self.mu) / self.sd
        d = dtw_many(x, self.X)
        best = self.y[int(np.argmin(d))]
        vi = np.flatnonzero(self.y != R.OTHER)
        top = self.y[vi[np.argmin(d[vi])]]
        return top, 1.0 / (1.0 + float(d[vi].min())), best == R.OTHER
