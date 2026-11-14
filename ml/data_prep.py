"""Download ASL Citizen hand landmarks for the vocab and cache them as .npy files.

Source: SorensenAI/asl-citizen-poses on Hugging Face (MediaPipe Holistic .pose files, one per
ASL Citizen clip). Official ASL Citizen train/val/test splits (signer-disjoint) come from
mage0001/ASLCitizen-3D samples.csv.

Output (resumable; existing files are skipped):
  ml/data/landmarks/<GLOSS>/<clip>.npy   float32 (T, 21, 3), MediaPipe-normalised x/W, y/H, raw z,
                                         NaN rows for frames with no hand detected
  ml/data/landmarks/splits.csv           clip path, gloss, source gloss, split, signer, frame counts

Directories whose name is a vocab gloss are positives; any other directory is used as
"not a vocab sign" (negative) data.

    python ml/data_prep.py                    # vocab signs + default negatives
    python ml/data_prep.py --negatives 0      # vocab signs only
"""
import argparse
import csv
import json
import random
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np

ML = Path(__file__).parent
DATA = ML / "data"
LANDMARKS = DATA / "landmarks"
RAW = DATA / "raw"
VOCAB = ML.parent / "shared" / "vocab.json"
POSE_REPO = "SorensenAI/asl-citizen-poses"
SPLIT_REPO = "mage0001/ASLCitizen-3D"

# ASL Citizen gloss (with variant numbers stripped) -> vocab gloss, where they differ.
ALIASES = {"FINISH": "ALL-DONE"}
# Different signs whose English overlaps the vocab: useful hard negatives.
HARD_NEGATIVES = ["HUNGRY", "THIRSTY", "TIRED", "BED", "FOOD", "DRINK", "PLEASE", "THANK YOU",
                  "MOTHER", "FATHER", "GOOD", "BATHROOM", "HOME", "NAME", "SORRY", "WHERE", "WHO"]


def _ssl():
    try:
        import truststore
        truststore.inject_into_ssl()
    except ImportError:
        pass


def base_gloss(name):
    """'MILK 2' -> 'MILK', 'WHAT 1' -> 'WHAT'."""
    parts = name.rsplit(" ", 1)
    return parts[0] if len(parts) == 2 and parts[1].isdigit() else name


def vocab_glosses():
    return [v["gloss"] for v in json.loads(VOCAB.read_text())]


def list_pose_files():
    cache = DATA / "_meta" / "pose_files.json"
    if cache.exists():
        return json.loads(cache.read_text())
    from huggingface_hub import HfApi
    files = [f for f in HfApi().list_repo_files(POSE_REPO, repo_type="dataset")
             if f.startswith("poses_batches/") and f.endswith(".pose")]
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(files))
    return files


def official_splits():
    from huggingface_hub import hf_hub_download
    p = hf_hub_download(SPLIT_REPO, "samples.csv", repo_type="dataset", local_dir=DATA / "_meta" / "split_repo")
    with open(p, newline="", encoding="utf8") as f:
        return {r["sample_id"]: r["split"] for r in csv.DictReader(f)}


def extract_hands(pose_path):
    """Returns the dominant hand as (T, 21, 3) MediaPipe-normalised coords with NaN where missing."""
    from pose_format import Pose
    pose = Pose.read(Path(pose_path).read_bytes())
    w, h = pose.header.dimensions.width, pose.header.dimensions.height
    names = [c.name for c in pose.header.components]
    offsets = np.cumsum([0] + [len(c.points) for c in pose.header.components])
    data = np.asarray(pose.body.data.filled(0))[:, 0]
    conf = np.asarray(pose.body.confidence)[:, 0]
    hands = []
    for comp in ("RIGHT_HAND_LANDMARKS", "LEFT_HAND_LANDMARKS"):
        i = names.index(comp)
        pts = data[:, offsets[i]:offsets[i + 1]].astype(np.float32).copy()
        present = conf[:, offsets[i]:offsets[i + 1]].sum(-1) > 0
        pts[..., 0] /= w
        pts[..., 1] /= h
        pts[~present] = np.nan
        motion = np.nanmean(np.linalg.norm(np.diff(pts[present][:, 0, :2], axis=0), axis=-1)) if present.sum() > 2 else 0.0
        hands.append((int(present.sum()), float(motion), comp, pts))
    # Dominant hand = detected in more frames; ties broken by more wrist motion.
    n, _, comp, pts = max(hands, key=lambda t: (t[0], t[1]))
    return pts, comp, n, data.shape[0]


def process(remote, gloss_dir, split):
    clip = Path(remote).stem
    out = LANDMARKS / gloss_dir / f"{clip}.npy"
    meta = out.with_suffix(".json")
    if out.exists() and meta.exists():
        return json.loads(meta.read_text())
    if meta.exists():                       # previously processed and skipped (no hand)
        return json.loads(meta.read_text())
    from huggingface_hub import hf_hub_download
    local = hf_hub_download(POSE_REPO, remote, repo_type="dataset", local_dir=RAW)
    pts, comp, n_detected, n_frames = extract_hands(local)
    out.parent.mkdir(parents=True, exist_ok=True)
    info = {"clip": clip, "gloss": gloss_dir, "source_gloss": clip.split("-", 1)[1], "split": split,
            "signer": "", "hand": comp, "n_frames": n_frames, "n_detected": n_detected, "kept": n_detected >= 4}
    if info["kept"]:
        np.save(out, pts)
    meta.write_text(json.dumps(info))
    return info


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--negatives", type=int, default=70, help="number of random non-vocab glosses to fetch")
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    _ssl()

    vocab = set(vocab_glosses())
    files = list_pose_files()
    splits = official_splits()
    by_gloss = {}
    for f in files:
        source = Path(f).stem.split("-", 1)[1]
        by_gloss.setdefault(base_gloss(source), []).append(f)

    target_of = {}
    for g in by_gloss:
        v = ALIASES.get(g, g)
        if v in vocab:
            target_of[g] = v
    missing = vocab - set(target_of.values())
    print("vocab glosses found:", sorted(set(target_of.values())), "missing:", sorted(missing))

    pool = sorted(g for g in by_gloss if g not in target_of and g not in HARD_NEGATIVES and len(by_gloss[g]) >= 20)
    rng = random.Random(args.seed)
    negatives = [g for g in HARD_NEGATIVES if g in by_gloss] + rng.sample(pool, min(args.negatives, len(pool)))
    if args.negatives == 0:
        negatives = []

    jobs = []
    for g, files_g in by_gloss.items():
        gloss_dir = target_of.get(g) or (g if g in negatives else None)
        if gloss_dir is None:
            continue
        for f in files_g:
            sid = Path(f).stem
            if sid not in splits:
                continue                     # not in the official split files; dropped
            jobs.append((f, gloss_dir, splits[sid]))
    print(f"{len(jobs)} clips to process ({len(negatives)} negative glosses)")

    rows, errors = [], 0
    with ThreadPoolExecutor(args.workers) as ex:
        futs = {ex.submit(process, *j): j for j in jobs}
        for i, fut in enumerate(as_completed(futs), 1):
            try:
                rows.append(fut.result())
            except Exception as e:           # keep going; rerun to retry failures
                errors += 1
                print("ERROR", futs[fut][0], type(e).__name__, e, file=sys.stderr)
            if i % 200 == 0:
                print(f"  {i}/{len(jobs)} done, {errors} errors", flush=True)

    rows.sort(key=lambda r: (r["gloss"], r["clip"]))
    with open(LANDMARKS / "splits.csv", "w", newline="", encoding="utf8") as f:
        w = csv.DictWriter(f, fieldnames=["path", "gloss", "source_gloss", "split", "signer", "hand",
                                          "n_frames", "n_detected", "kept"])
        w.writeheader()
        for r in rows:
            w.writerow({"path": f"{r['gloss']}/{r['clip']}.npy", **{k: r[k] for k in w.fieldnames if k != "path"}})
    print(f"done: {sum(r['kept'] for r in rows)} kept, {sum(not r['kept'] for r in rows)} skipped (no hand), {errors} errors")


if __name__ == "__main__":
    main()
