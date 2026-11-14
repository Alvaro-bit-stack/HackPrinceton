# Overnight log: sign-recognition model

_(Summary will be written here at the end of the run.)_

## Requested changes outside ml/

1. **`frontend/src/components/Webcam.jsx`: `WINDOW = 15` is too short.** At requestAnimationFrame rate that is 0.25-0.5 s, less than one sign. Suggest ~45-60 frames (~1.5-2 s), or a time-based window. The model resamples any length to 32 steps, so no backend change is needed.
2. **`Webcam.jsx`: keep the same hand across frames.** `hands[0]` can switch between the two hands from frame to frame. Better: pick the hand by `result.handedness` (or the one closest to the previous wrist) and keep it. `ml/recognizer.py` already has a workaround (`keep_one_hand`).
3. (Optional) Only send frames while a hand is visible and reset the buffer when the hand disappears for >0.5 s, so a window holds one attempt rather than the tail of the previous one.
4. No backend change is needed: inference uses only numpy, which is already in `backend/requirements.txt`.

## Timeline

### 2026-11-14 00:00 Setup
- Created branch `overnight-sign-model` from `main` (a5ff556).
- Repo state: `ml/` contains only `recognizer.py`, `README.md`, `__init__.py`. No `templates.json`, no `ml/data/`. So no local data exists.
- Machine: Windows, Python 3.11.9, **no GPU** (CPU-only training).
- Created `ml/.gitignore` (venv, data/, videos, parquet, caches, per-epoch checkpoints).

### 2026-11-14 00:08 Environment
- **Error:** `pip install` failed with `SSL: CERTIFICATE_VERIFY_FAILED`. Cause: AVG antivirus intercepts TLS (`SSLKEYLOGFILE=\\.\avgMonFltProxy\...`). Its root cert is in the Windows store but not in pip's certifi bundle.
- **Fix (no system changes):** `pip install --use-feature=truststore --upgrade pip` (pip 24.0 -> 26.3; pip >= 24.2 uses the OS trust store by default). Verification stays ON; nothing was set to `--trusted-host`.
- Python code that downloads data calls `truststore.inject_into_ssl()` for the same reason.
- Installed into `ml/.venv`: torch 2.15.0+cpu, numpy 2.4.6, scikit-learn 1.9.1, mediapipe 1.2.3, opencv-python-headless, pandas, pyarrow, requests, huggingface_hub, truststore.

### 2026-11-14 00:20 Phase 1: dataset search
- Local data in `ml/`: none (no `templates.json`, no `ml/data/`).
- Google ISLR (Kaggle "asl-signs"): **not used**. Needs Kaggle login + accepting competition rules; no credentials on this machine. Also covers only ~7 of the 15 vocab signs (no MORE, HELP, WANT, YOU, ME, LOVE, WHAT, PLAY).
- WLASL: videos are mostly YouTube links (many dead) and would need MediaPipe extraction; not needed given the option below.
- **Chosen: ASL Citizen** (Microsoft Research, Desai et al. 2023; 83k clips, 2.7k signs, 52 crowd-sourced signers recording on their own webcams). Used via:
  - `SorensenAI/asl-citizen-poses` (Hugging Face): one MediaPipe Holistic `.pose` file per clip, gloss in the filename, so only the vocab clips need downloading. Hand landmarks are the same 21-point MediaPipe topology the browser uses.
  - `mage0001/ASLCitizen-3D/samples.csv`: the official ASL Citizen train/val/test assignment per clip. The ASL Citizen paper defines these splits as **signer-disjoint**. Per-clip participant IDs are not in any public mirror I could find (searched HF for "asl citizen" csvs), so the split is by signer but per-signer results cannot be computed.
  - License: ASL Citizen is released under Microsoft's research dataset license (non-commercial research use). **Review before any commercial use.** Data stays in `ml/data/` (git-ignored); only the trained weights are committed.
- All 15 vocab glosses exist in ASL Citizen (33-43 clips per variant). Mapping decisions:
  - `ALL-DONE` <- ASL Citizen `FINISH` (the "all done" sign is FINISH).
  - Variant numbers are merged: `MILK`+`MILK 2`, `EAT`+`EAT 2`, `WANT`+`WANT 2`, `WHAT 1`+`WHAT 2`. A child could use either form; merging keeps every accepted form under one label.
  - `EAT` uses only the EAT sign; `SLEEP` only SLEEP. HUNGRY, THIRSTY, TIRED, BED are different signs and are used as **hard negatives**, not positives.
- Negatives ("not a vocab sign"): the 17 hard-negative glosses (where present) + 70 random other glosses (seed 0). Used as an `_OTHER` class and to measure false accepts.

### 2026-11-14 00:30 Phase 1: format checks and design decisions
- `.pose` stores x*width, y*height, raw z. `data_prep.py` divides back by width/height, so cached landmarks are exactly what MediaPipe JS returns in the browser (normalised image coords).
- Read (not edited) `frontend/src/components/Webcam.jsx` + `handTracker.js`: the browser sends `hands[0]` of each frame (can flip between left and right hand) in a rolling **15-frame window** (~0.25-0.5 s at display rate). A full sign is ~1-1.5 s. See "Requested changes outside ml/".
- `normalize()` puts the wrist at the origin per frame, which erases the hand's travel path. Kept `normalize()` unchanged and added 3 per-frame features computed the same way at train and inference time: wrist path relative to the clip's mean position, divided by median hand size (2), and log of hand size relative to its median (1, toward/away from camera). Still invariant to where the hand is and how big it is.
- Location relative to the body (chin vs chest) cannot be recovered: the browser sends no face/body landmarks.
- Training picks one hand per clip (the one detected in more frames). Mirror augmentation makes the model work for either hand; no vocab sign differs from another only by handedness, so mirroring is label-safe.
- Inference runs in **pure numpy** (`model.npz`) because `backend/requirements.txt` has no torch and I can't edit it. Torch is only needed for training.
- `recognizer.py` rewritten: same `normalize`, `load_templates`, `add_template`, `predict(frames, templates=None)`. Added input sanitising, hand-switch cleanup (`keep_one_hand`), `sequence_features`, numpy CNN inference, template fallback. Self-check extended (edge cases + movement-only pair: last-frame baseline 0/8, sequence features 8/8). Passes.
- `data_prep.py` started: 3432 clips (vocab + 86 negative glosses), 12 threads, resumable.
