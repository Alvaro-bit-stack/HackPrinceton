"""Add WLASL clips of the vocab signs as extra training data (more signers).

Videos come from Voxel51/WLASL on Hugging Face; signer ids from WLASL_v0.3.json (github.com/dxli94/WLASL).
Hand landmarks are extracted with MediaPipe HandLandmarker (the same model the browser runs), VIDEO mode,
2 hands, then the hand detected in more frames is kept. Resumable: finished clips are skipped.

Output: ml/data/landmarks/<GLOSS>/wlasl<signer>__<video_id>.npy (+ .json), and rows appended to
ml/data/landmarks/splits.csv with split=train (validation and test stay ASL Citizen only).

    python ml/wlasl_prep.py
"""
import csv
import json
from pathlib import Path

import numpy as np

ML = Path(__file__).parent
DATA = ML / "data"
LANDMARKS = DATA / "landmarks"
MODEL_URL = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"
WLASL_JSON = "https://raw.githubusercontent.com/dxli94/WLASL/master/start_kit/WLASL_v0.3.json"
TO_VOCAB = {"milk": "MILK", "more": "MORE", "eat": "EAT", "water": "WATER", "sleep": "SLEEP", "help": "HELP",
            "finish": "ALL-DONE", "want": "WANT", "you": "YOU", "me": "ME", "love": "LOVE", "what": "WHAT",
            "yes": "YES", "no": "NO", "play": "PLAY"}


def fetch(url, path):
    import requests
    path = Path(path)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        r = requests.get(url, timeout=120)
        r.raise_for_status()
        path.write_bytes(r.content)
    return path


def extract(video, landmarker_path):
    import cv2
    import mediapipe as mp
    from mediapipe.tasks.python import BaseOptions, vision
    opts = vision.HandLandmarkerOptions(base_options=BaseOptions(model_asset_path=str(landmarker_path)),
                                        running_mode=vision.RunningMode.VIDEO, num_hands=2)
    cap = cv2.VideoCapture(str(video))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    tracks = {"Left": [], "Right": []}
    with vision.HandLandmarker.create_from_options(opts) as lm:
        i = 0
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            img = mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            res = lm.detect_for_video(img, int(i * 1000 / fps))
            seen = {}
            for hand, hd in zip(res.hand_landmarks, res.handedness):
                seen.setdefault(hd[0].category_name, np.array([[p.x, p.y, p.z] for p in hand], np.float32))
            for k in tracks:
                tracks[k].append(seen.get(k, np.full((21, 3), np.nan, np.float32)))
            i += 1
    cap.release()
    best = None
    for k, t in tracks.items():
        t = np.stack(t) if t else np.zeros((0, 21, 3), np.float32)
        n = int((~np.isnan(t[:, 0, 0])).sum()) if len(t) else 0
        if best is None or n > best[1]:
            best = (k, n, t)
    return best


def main():
    try:
        import truststore
        truststore.inject_into_ssl()
    except ImportError:
        pass
    from huggingface_hub import hf_hub_download
    landmarker = fetch(MODEL_URL, DATA / "models" / "hand_landmarker.task")
    info = {}
    for e in json.loads(fetch(WLASL_JSON, DATA / "_meta" / "wlasl" / "WLASL_v0.3.json").read_text()):
        for inst in e["instances"]:
            info[inst["video_id"]] = (e["gloss"], inst["signer_id"], inst.get("variation_id"))
    samples = json.loads(Path(hf_hub_download("Voxel51/WLASL", "samples.json", repo_type="dataset",
                                              local_dir=DATA / "_meta" / "wlasl")).read_text())["samples"]
    rows = []
    for s in samples:
        label = s["gloss"]["label"]
        if label not in TO_VOCAB:
            continue
        vid = Path(s["filepath"]).stem
        gloss, signer, variation = info.get(vid, (label, "unknown", None))
        out = LANDMARKS / TO_VOCAB[label] / f"wlasl{signer}__{vid}.npy"
        meta = out.with_suffix(".json")
        if not meta.exists():
            video = hf_hub_download("Voxel51/WLASL", s["filepath"], repo_type="dataset", local_dir=DATA / "raw" / "wlasl")
            hand, n, seq = extract(video, landmarker)
            m = {"clip": out.stem, "gloss": TO_VOCAB[label], "source_gloss": f"wlasl:{label}:v{variation}",
                 "split": "train", "signer": f"wlasl{signer}", "hand": hand, "n_frames": len(seq),
                 "n_detected": n, "kept": n >= 4}
            out.parent.mkdir(parents=True, exist_ok=True)
            if m["kept"]:
                np.save(out, seq)
            meta.write_text(json.dumps(m))
            print(f"{out.parent.name}/{out.name}: {n}/{len(seq)} frames with a hand ({hand})", flush=True)
        rows.append(json.loads(meta.read_text()))

    split_file = LANDMARKS / "splits.csv"
    with open(split_file, newline="", encoding="utf8") as f:
        existing = [r for r in csv.DictReader(f) if not r["path"].split("/")[-1].startswith("wlasl")]
    fields = ["path", "gloss", "source_gloss", "split", "signer", "hand", "n_frames", "n_detected", "kept"]
    with open(split_file, "w", newline="", encoding="utf8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(existing)
        for r in rows:
            w.writerow({"path": f"{r['gloss']}/{r['clip']}.npy", **{k: r[k] for k in fields if k != "path"}})
    print(f"WLASL: {sum(r['kept'] for r in rows)} kept, {sum(not r['kept'] for r in rows)} skipped (no hand)")


if __name__ == "__main__":
    main()
