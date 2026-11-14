"""Train the sign-recognition model and export it for recognizer.py.

    ml/.venv/Scripts/python ml/train.py                 # baselines + default sweep, writes ml/model.npz
    ml/.venv/Scripts/python ml/train.py --no-baselines --configs base

Steps: load ml/data/landmarks (see dataset.py for the format), run Baselines A and B on the validation
split, train Model C (1D-CNN over 32 resampled frames, with augmentation, early stopping, a checkpoint
per epoch), pick the best config on validation accuracy, fit a softmax temperature and the
MIN_CONFIDENCE threshold on validation, then export ml/model.npz (numpy weights, batch-norm folded).
The test split is never touched here; run evaluate.py once afterwards.
"""
import argparse
import csv
import json
import random
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn

import baselines as B
import dataset as D
import metrics as M
import recognizer as R

ML = Path(__file__).parent
RESULTS = ML / "results"
CHECKPOINTS = ML / "checkpoints"
LOG = ML / "OVERNIGHT_LOG.md"

CONFIGS = {
    "base":   dict(width=96, dilations=(1, 2, 4), dropout=0.3, lr=2e-3, weight_decay=1e-3),
    "small":  dict(width=64, dilations=(1, 2), dropout=0.2, lr=2e-3, weight_decay=1e-3),
    "wide":   dict(width=128, dilations=(1, 2, 4), dropout=0.4, lr=1.5e-3, weight_decay=3e-3),
}


def log(msg):
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    print(msg, flush=True)
    with open(LOG, "a", encoding="utf8") as f:
        f.write(f"- `{stamp}` [train.py] {msg}\n")


def seed_all(seed):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)


class SignCNN(nn.Module):
    """Conv1d -> BatchNorm -> ReLU blocks, then mean+max pooling over time and a linear classifier.
    recognizer.model_logits() runs the exported version of exactly this in numpy."""
    def __init__(self, in_dim, n_classes, width=96, dilations=(1, 2, 4), k=5, dropout=0.3, **_):
        super().__init__()
        layers, c = [], in_dim
        for d in dilations:
            layers += [nn.Conv1d(c, width, k, padding=d * (k // 2), dilation=d), nn.BatchNorm1d(width), nn.ReLU()]
            c = width
        self.convs = nn.Sequential(*layers)
        self.drop = nn.Dropout(dropout)
        self.fc = nn.Linear(2 * width, n_classes)
        self.dilations = tuple(dilations)

    def forward(self, x):                       # x: (B, T, F) standardised features
        h = self.convs(x.transpose(1, 2))
        pooled = torch.cat([h.mean(2), h.amax(2)], dim=1)
        return self.fc(self.drop(pooled))


def build_features(clips, rng=None, aug=False):
    X, keep = [], []
    for i, c in enumerate(clips):
        f = D.features(D.augment(c.seq, rng)) if aug else None
        if f is None:
            f = D.features(c.seq)
        if f is not None:
            X.append(f)
            keep.append(i)
    return np.stack(X), keep


def scores_from_probs(probs, classes):
    """-> (best vocab gloss, its prob, argmax is _OTHER) per row."""
    vocab_idx = [i for i, c in enumerate(classes) if c != R.OTHER]
    other_idx = classes.index(R.OTHER) if R.OTHER in classes else None
    pv = probs[:, vocab_idx]
    best = np.array([classes[vocab_idx[i]] for i in pv.argmax(1)], dtype=object)
    conf = pv.max(1)
    is_other = probs.argmax(1) == other_idx if other_idx is not None else np.zeros(len(probs), bool)
    return best, conf, is_other


def train_one(name, cfg, train, val, classes, stats, args):
    seed_all(args.seed)
    rng = np.random.default_rng(args.seed)
    cidx = {c: i for i, c in enumerate(classes)}
    mean, std = stats
    model = SignCNN(mean.shape[-1], len(classes), **cfg)
    opt = torch.optim.AdamW(model.parameters(), lr=cfg["lr"], weight_decay=cfg["weight_decay"])
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=args.epochs)
    lossf = nn.CrossEntropyLoss(label_smoothing=0.05)

    pos = [c for c in train if c.label != R.OTHER]
    neg = [c for c in train if c.label == R.OTHER]
    n_other = int(args.other_ratio * len(pos) / max(1, len(classes) - 1)) if neg else 0

    Xv, kv = build_features(val)
    yv = np.array([cidx[val[i].label] for i in kv])
    Xv_t = torch.tensor((Xv - mean) / std, dtype=torch.float32)
    true_v = [val[i].label for i in kv]

    ckdir = CHECKPOINTS / name
    ckdir.mkdir(parents=True, exist_ok=True)
    history, best, bad, t0 = [], None, 0, time.time()
    for epoch in range(1, args.epochs + 1):
        model.train()
        batch_clips = pos * args.repeats + (list(rng.choice(neg, size=min(len(neg), n_other * args.repeats), replace=False)) if neg else [])
        X, kept = build_features(batch_clips, rng, aug=True)
        y = np.array([cidx[batch_clips[i].label] for i in kept])
        X = torch.tensor((X - mean) / std, dtype=torch.float32)
        y = torch.tensor(y)
        order = torch.randperm(len(y))
        tot = 0.0
        for s in range(0, len(y), args.batch):
            idx = order[s:s + args.batch]
            opt.zero_grad()
            loss = lossf(model(X[idx]), y[idx])
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 5.0)
            opt.step()
            tot += float(loss.detach()) * len(idx)
        sched.step()

        model.eval()
        with torch.no_grad():
            logits = model(Xv_t)
            vloss = float(nn.functional.cross_entropy(logits, torch.tensor(yv)))
            probs = torch.softmax(logits, 1).numpy()
        pred, conf, other = scores_from_probs(probs, classes)
        s = M.summarize(true_v, pred, conf, other, 0.0)
        row = {"epoch": epoch, "train_loss": tot / len(y), "val_loss": vloss, "val_acc": s["closed_set_accuracy"],
               "val_other_reject": 1 - s["false_accept_rate_other"] if s["n_other_clips"] else float("nan")}
        history.append(row)
        torch.save({"model": model.state_dict(), "cfg": cfg, "epoch": epoch}, ckdir / f"epoch_{epoch:03d}.pt")
        key = (row["val_acc"], -row["val_loss"])
        if best is None or key > best[0]:
            best, bad = (key, epoch, {k: v.clone() for k, v in model.state_dict().items()}), 0
        else:
            bad += 1
        if epoch % 10 == 0 or epoch == 1:
            print(f"  [{name}] epoch {epoch:3d} train_loss {row['train_loss']:.3f} val_loss {vloss:.3f} "
                  f"val_acc {row['val_acc']:.3f} other_reject {row['val_other_reject']:.3f}", flush=True)
        if not np.isfinite(row["train_loss"]):
            log(f"{name}: training loss diverged at epoch {epoch}; stopping this run")
            break
        if bad >= args.patience:
            break
        if time.time() - t0 > args.max_minutes * 60:
            log(f"{name}: hit the {args.max_minutes}-minute cap at epoch {epoch}")
            break
    model.load_state_dict(best[2])
    torch.save({"model": model.state_dict(), "cfg": cfg, "epoch": best[1]}, ckdir / "best.pt")
    with open(RESULTS / f"history_{name}.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(history[0]))
        w.writeheader()
        w.writerows(history)
    hb = history[best[1] - 1]
    log(f"Model C `{name}` {cfg}: best epoch {best[1]}/{len(history)}, val_acc {hb['val_acc']:.3f}, "
        f"val_loss {hb['val_loss']:.3f}, {time.time() - t0:.0f}s")
    return model, hb


def fit_temperature(logits, y):
    best_t, best_nll = 1.0, np.inf
    for t in np.exp(np.linspace(np.log(0.3), np.log(5), 120)):
        z = logits / t
        z = z - z.max(1, keepdims=True)
        nll = float(-(z[np.arange(len(y)), y] - np.log(np.exp(z).sum(1))).mean())
        if nll < best_nll:
            best_t, best_nll = float(t), nll
    return best_t, best_nll


def export(model, classes, stats, temperature, min_conf, path):
    """Fold batch-norm into the convs and save numpy arrays that recognizer.model_logits() reads."""
    model.eval()
    arrays, i = {}, 0
    mods = list(model.convs)
    for j in range(0, len(mods), 3):
        conv, bn = mods[j], mods[j + 1]
        g = (bn.weight / torch.sqrt(bn.running_var + bn.eps)).detach()
        arrays[f"w{i}"] = (conv.weight.detach() * g[:, None, None]).numpy().astype(np.float32)
        arrays[f"b{i}"] = ((conv.bias.detach() - bn.running_mean) * g + bn.bias.detach()).numpy().astype(np.float32)
        i += 1
    np.savez_compressed(
        path, **arrays, n_layers=np.int64(i), dilations=np.array(model.dilations, dtype=np.int64),
        fc_w=model.fc.weight.detach().numpy().astype(np.float32), fc_b=model.fc.bias.detach().numpy().astype(np.float32),
        mean=stats[0].astype(np.float32), std=stats[1].astype(np.float32), classes=np.array(classes),
        temperature=np.float64(temperature), min_confidence=np.float64(min_conf), seq_len=np.int64(R.SEQ_LEN))


def run_baselines(train, val):
    out = {}
    for model in (B.LastFrameNN(), B.SequenceKNN(5), B.SequenceDTW()):
        t0 = time.time()
        model.fit(train)
        rows = [model.score(c.seq) for c in val]
        true = [c.label for c in val]
        pred = [r[0] for r in rows]
        conf = [r[1] for r in rows]
        other = [r[2] for r in rows]
        tau, met = M.choose_threshold(true, pred, conf, other, 0.90)
        out[model.name] = {"val_at_0": M.summarize(true, pred, conf, other, 0.0),
                           "val_at_tau": M.summarize(true, pred, conf, other, tau), "tau": tau, "met_target": met}
        a = out[model.name]
        log(f"{model.name}: val closed-set acc {a['val_at_0']['closed_set_accuracy']:.3f}; "
            f"threshold {tau:.2f} -> precision {a['val_at_tau']['precision']:.3f}, coverage {a['val_at_tau']['coverage']:.3f} "
            f"({time.time() - t0:.0f}s)")
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--configs", default="base,small,wide", help=f"comma list from {list(CONFIGS)}")
    ap.add_argument("--epochs", type=int, default=150)
    ap.add_argument("--patience", type=int, default=30)
    ap.add_argument("--max-minutes", type=float, default=45)
    ap.add_argument("--batch", type=int, default=64)
    ap.add_argument("--repeats", type=int, default=2, help="augmented copies of each training clip per epoch")
    ap.add_argument("--other-ratio", type=float, default=3.0, help="_OTHER clips per epoch, in average-class units")
    ap.add_argument("--target-precision", type=float, default=0.90)
    ap.add_argument("--no-baselines", action="store_true")
    ap.add_argument("--no-other", action="store_true", help="train without the 'not a vocab sign' class")
    ap.add_argument("--out", default=str(ML / "model.npz"))
    args = ap.parse_args()
    seed_all(args.seed)
    torch.set_num_threads(max(1, torch.get_num_threads()))
    RESULTS.mkdir(exist_ok=True)

    clips = D.load_clips(include_other=not args.no_other)
    train = [c for c in clips if c.split == "train"]
    val = [c for c in clips if c.split == "val"]
    if not train or not val:
        raise SystemExit("No training data. Put clips in ml/data/landmarks/<GLOSS>/*.npy (see dataset.py) "
                         "or run ml/data_prep.py.")
    classes = sorted({c.label for c in clips if c.label != R.OTHER})
    if any(c.label == R.OTHER for c in train):
        classes.append(R.OTHER)
    log(f"data: {len(train)} train / {len(val)} val clips, {len(classes)} classes "
        f"({sum(c.label != R.OTHER for c in train)} / {sum(c.label != R.OTHER for c in val)} are vocab signs)")

    summary = {"args": vars(args), "classes": classes}
    if not args.no_baselines:
        summary["baselines"] = run_baselines(train, val)

    Xtr, _ = build_features(train)
    mean, std = Xtr.reshape(-1, Xtr.shape[-1]).mean(0), Xtr.reshape(-1, Xtr.shape[-1]).std(0) + 1e-6
    runs = {}
    for name in args.configs.split(","):
        try:
            model, hb = train_one(name, CONFIGS[name], train, val, classes, (mean, std), args)
            runs[name] = (model, hb)
        except Exception as e:
            log(f"Model C `{name}` crashed: {type(e).__name__}: {e}. Skipping this config.")
    if not runs:
        raise SystemExit("all training runs failed")
    name = max(runs, key=lambda n: (runs[n][1]["val_acc"], -runs[n][1]["val_loss"]))
    model = runs[name][0]
    summary["model_c"] = {n: h for n, (_, h) in runs.items()}
    summary["chosen"] = name
    log(f"chosen config: `{name}` (val_acc {runs[name][1]['val_acc']:.3f})")

    # Calibrate on validation: temperature, then threshold for target precision.
    Xv, kv = build_features(val)
    cidx = {c: i for i, c in enumerate(classes)}
    yv = np.array([cidx[val[i].label] for i in kv])
    model.eval()
    with torch.no_grad():
        logits = model(torch.tensor((Xv - mean) / std, dtype=torch.float32)).numpy()
    T, nll = fit_temperature(logits, yv)
    z = logits / T
    probs = np.exp(z - z.max(1, keepdims=True))
    probs /= probs.sum(1, keepdims=True)
    true_v = [val[i].label for i in kv]
    pred, conf, other = scores_from_probs(probs, classes)
    tau, met = M.choose_threshold(true_v, pred, conf, other, args.target_precision)
    if not met:
        log(f"WARNING: no threshold reached {args.target_precision:.0%} validation precision; using the most precise one ({tau:.2f})")
    at = M.summarize(true_v, pred, conf, other, tau)
    summary["calibration"] = {"temperature": T, "val_nll": nll, "min_confidence": tau, "met_target": met,
                              "val_at_threshold": at, "val_tradeoff": M.tradeoff(true_v, pred, conf, other)}
    log(f"temperature {T:.2f} (val NLL {nll:.3f}); MIN_CONFIDENCE {tau:.2f} -> val precision {at['precision']:.3f}, "
        f"coverage {at['coverage']:.3f}, false accepts on non-vocab {at['false_accept_rate_other']:.3f}")

    export(model, classes, (mean, std), T, tau, args.out)
    R._model_cache.clear()
    m = R.load_model(args.out)
    np_probs = np.stack([R.model_probs(m, x) for x in Xv])
    diff = float(np.abs(np_probs - probs).max())
    assert diff < 1e-3, f"numpy export disagrees with torch (max prob diff {diff})"
    log(f"exported {args.out} ({Path(args.out).stat().st_size / 1024:.0f} KB); numpy vs torch max prob diff {diff:.2e}")

    # Regression clips for the recognizer self-check: one correctly accepted validation clip per sign.
    picks = {}
    for j, i in enumerate(kv):
        c = val[i]
        if c.label != R.OTHER and c.label not in picks and pred[j] == c.label and not other[j] and conf[j] >= tau:
            picks[c.label] = c
    if picks:
        seqs = []
        for p in picks.values():
            v = np.flatnonzero(~np.isnan(p.seq[:, 0, 0]))
            seqs.append(p.seq[v[0]:v[-1] + 1])
        L = max(len(s) for s in seqs)
        frames = np.zeros((len(seqs), L, 21, 3), np.float32)
        for k, s in enumerate(seqs):
            frames[k, :len(s)] = s
        np.savez_compressed(ML / "model_selfcheck.npz", frames=frames, lengths=np.array([len(s) for s in seqs]),
                            labels=np.array(list(picks)))
    (RESULTS / "train_summary.json").write_text(json.dumps(summary, indent=2, default=float))
    log(f"done; summary in results/train_summary.json")


if __name__ == "__main__":
    main()
