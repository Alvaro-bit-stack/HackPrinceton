"""Evaluate ml/model.npz (exactly as recognizer.predict runs it) and the baselines on the test split,
and write the accuracy table.

    ml/.venv/Scripts/python ml/evaluate.py              # -> ml/results/test_results.json, ml/results/accuracy_table.md

Run once after train.py has chosen a model; the test split is never used for any choice.
"""
import argparse
import json
from pathlib import Path

import numpy as np

import baselines as B
import dataset as D
import metrics as M
import recognizer as R

ML = Path(__file__).parent
RESULTS = ML / "results"


def model_scores(m, seqs):
    classes = [str(c) for c in m["classes"]]
    vocab_idx = [i for i, c in enumerate(classes) if c != R.OTHER]
    out = []
    for s in seqs:
        x = R.sequence_features(s, int(m["seq_len"]))
        if x is None:
            out.append((None, 0.0, True))
            continue
        p = R.model_probs(m, x)
        j = vocab_idx[int(np.argmax(p[vocab_idx]))]
        out.append((classes[j], float(p[j]), classes[int(np.argmax(p))] == R.OTHER))
    return out


def unpack(rows):
    return [r[0] for r in rows], [r[1] for r in rows], [r[2] for r in rows]


def fmt(v, pct=True):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "–"
    return f"{100 * v:.0f}%" if pct else f"{v}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="test")
    ap.add_argument("--model", default=str(ML / "model.npz"))
    ap.add_argument("--window", type=int, default=15, help="frames in the browser-like short-window evaluation")
    args = ap.parse_args()
    RESULTS.mkdir(exist_ok=True)

    m = R.load_model(args.model)
    if m is None:
        raise SystemExit(f"{args.model} not found; run train.py first")
    tau = float(m["min_confidence"])
    clips = D.load_clips()
    train = [c for c in clips if c.split == "train"]
    test = [c for c in clips if c.split == args.split]
    glosses = sorted({c.label for c in test if c.label != R.OTHER})
    true = [c.label for c in test]
    res = {"split": args.split, "min_confidence": tau, "temperature": float(m["temperature"]),
           "n_clips": len(test), "n_sign_clips": sum(t != R.OTHER for t in true)}

    # Model C, full clips, through the same code path as predict()
    pred, conf, other = unpack(model_scores(m, [c.seq for c in test]))
    for c, p_, k_, o_ in list(zip(test, pred, conf, other))[:25]:          # spot-check against predict()
        r = R.predict(list(c.seq))
        assert r["sign"] == (p_ if (not o_ and k_ >= tau) else None), (c.path, r, p_, k_, o_)
    res["model_c"] = M.summarize(true, pred, conf, other, tau)
    res["model_c_per_sign"] = M.per_sign(true, pred, conf, other, tau, glosses)
    res["model_c_tradeoff"] = M.tradeoff(true, pred, conf, other)
    res["model_c_confusions"] = [[a, b, n] for (a, b), n in M.confusions(true, pred)]
    fa = {}
    for c, p_, k_, o_ in zip(test, pred, conf, other):
        if c.label == R.OTHER and not o_ and k_ >= tau:
            key = f"{c.source_gloss} -> {p_}"
            fa[key] = fa.get(key, 0) + 1
    res["model_c_false_accepts"] = sorted(fa.items(), key=lambda kv: -kv[1])[:15]
    res["model_c_by_variant"] = {}
    for c, p_ in zip(test, pred):
        if c.label != R.OTHER:
            d = res["model_c_by_variant"].setdefault(c.source_gloss, [0, 0])
            d[0] += p_ == c.label
            d[1] += 1

    # Model C on browser-like short windows (what the frontend currently sends)
    wins = [D.browser_window(c.seq, args.window) for c in test]
    res["model_c_window"] = M.summarize(true, *unpack(model_scores(m, wins)), tau)

    # Baselines on the same clips, each at its own validation-chosen threshold (from train_summary.json)
    summary_path = RESULTS / "train_summary.json"
    val_taus = {}
    if summary_path.exists():
        val_taus = {k: v["tau"] for k, v in json.loads(summary_path.read_text()).get("baselines", {}).items()}
    res["baselines"] = {}
    for bm in (B.LastFrameNN(), B.SequenceKNN(5), B.SequenceDTW()):
        bm.fit(train)
        p_, k_, o_ = unpack([bm.score(c.seq) for c in test])
        t = val_taus.get(bm.name, 0.0)
        res["baselines"][bm.name] = {"at_val_threshold": M.summarize(true, p_, k_, o_, t)}
        if isinstance(bm, B.LastFrameNN):
            res["baselines"][bm.name]["at_original_0.6"] = M.summarize(true, p_, k_, o_, 0.6)
            res["baseline_a_per_sign"] = M.per_sign(true, p_, k_, o_, t, glosses)
            res["baseline_a_window"] = M.summarize(true, *unpack([bm.score(w) for w in wins]), t)
        print(bm.name, "done", flush=True)

    (RESULTS / f"{args.split}_results.json").write_text(json.dumps(res, indent=2, default=float))
    table = render(res, glosses)
    (RESULTS / "accuracy_table.md").write_text(table, encoding="utf8")
    print(table)


def render(res, glosses):
    a_rows = {r["sign"]: r for r in res["baseline_a_per_sign"]}
    L = [f"Split: **{res['split']}** ({res['n_sign_clips']} clips of vocab signs, "
         f"{res['n_clips'] - res['n_sign_clips']} clips of other signs). "
         f"Model threshold MIN_CONFIDENCE = {res['min_confidence']:.2f} (chosen on validation).", "",
         "| Sign | Test clips | Accuracy (top-1) | Coverage (answers given) | Answered and right | Precision on vocab attempts | Non-vocab clips answered as this sign | Baseline A accuracy |",
         "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for r in res["model_c_per_sign"]:
        L.append(f"| {r['sign']} | {r['n']} | {fmt(r['accuracy'])} | {fmt(r['coverage'])} | {fmt(r['accepted_correct'])} | "
                 f"{fmt(r['precision_vocab'])} ({r['n_predicted_vocab']}) | {r['other_answered_as']} | "
                 f"{fmt(a_rows[r['sign']]['accuracy'])} |")
    c = res["model_c"]
    L.append(f"| **All signs** | {c['n_sign_clips']} | **{fmt(c['closed_set_accuracy'])}** | {fmt(c['coverage'])} | "
             f"{fmt(c['accepted_correct_rate'])} | {fmt(c['precision_vocab_only'])} | "
             f"{round(c['false_accept_rate_other'] * c['n_other_clips'])} of {c['n_other_clips']} | "
             f"{fmt(res['baselines']['A: last-frame NN (original)']['at_val_threshold']['closed_set_accuracy'])} |")
    L += ["", f"Overall precision when it answers, with non-vocab attempts weighted to equal vocab attempts (1:1): "
              f"**{fmt(c['precision'])}** (validation target was 90%). Unweighted, with all {c['n_other_clips']} non-vocab "
              f"clips at their real 5:1 ratio: {fmt(c['precision_unweighted'])}. Non-vocab clips that got a (wrong) vocab "
              f"answer: {fmt(c['false_accept_rate_other'])}.", "",
          "**Model comparison (same test clips; each at its own validation-chosen threshold):**", "",
          "| Model | Top-1 accuracy | Precision when it answers | Coverage | Non-vocab clips wrongly answered |",
          "|---|---:|---:|---:|---:|"]
    for name, b in res["baselines"].items():
        s = b["at_val_threshold"]
        L.append(f"| {name} | {fmt(s['closed_set_accuracy'])} | {fmt(s['precision'])} | {fmt(s['coverage'])} | "
                 f"{fmt(s['false_accept_rate_other'])} |")
    L.append(f"| **C: 1D-CNN sequence model (chosen)** | **{fmt(c['closed_set_accuracy'])}** | **{fmt(c['precision'])}** | "
             f"**{fmt(c['coverage'])}** | **{fmt(c['false_accept_rate_other'])}** |")
    w, aw = res["model_c_window"], res["baseline_a_window"]
    L += ["", f"**Short browser-like windows** (middle {15} frames of each clip, like `Webcam.jsx` sends today): "
              f"Model C accuracy {fmt(w['closed_set_accuracy'])}, precision {fmt(w['precision'])}, coverage {fmt(w['coverage'])}; "
              f"Baseline A accuracy {fmt(aw['closed_set_accuracy'])}.", "",
          "**Coverage vs precision (Model C, test):**", "",
          "| Threshold | Precision | Coverage | Non-vocab wrongly answered |", "|---:|---:|---:|---:|"]
    for t in res["model_c_tradeoff"]:
        L.append(f"| {t['threshold']:.2f} | {fmt(t['precision'])} | {fmt(t['coverage'])} | {fmt(t['false_accept_rate_other'])} |")
    L += ["", "**Most frequent confusions (true -> predicted, top-1, test):** " +
          (", ".join(f"{a} -> {b} ({n})" for a, b, n in res["model_c_confusions"]) or "none"),
          "", "**Non-vocab signs most often answered as a vocab sign (test, at the threshold):** " +
          (", ".join(f"{k} ({n})" for k, n in res["model_c_false_accepts"]) or "none")]
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    main()
