# Overnight log: sign-recognition model

## Summary (read this first)

Branch `overnight-sign-model`, 4 commits on top of `main` (a5ff556). Only files under `ml/` changed. Run time was about 1 hour; I stopped after Phase 5 as instructed.

**What worked**
- `predict()` now uses a small 1D-CNN over the whole frame sequence: 65k parameters, 240 KB `ml/model.npz`. It runs in pure numpy (about 4 ms per call), so the backend needs no new dependency.
  - The signature and output are unchanged.
  - It falls back to the original template nearest-neighbour if the model file is missing.
  - It returns `{"sign": None, "confidence": 0.0}` on empty, short, NaN, or misshapen input.
- **Data:** ASL Citizen hand landmarks for all 15 vocab signs, using the official signer-disjoint split. WLASL clips of the vocab signs (32 more signers) were added to training only. 86 other signs serve as "not a vocab sign" examples.
- **Test results** (evaluated once, unseen signers, 233 vocab clips):

  | Model | Top-1 accuracy |
  |---|---:|
  | Baseline A, original last frame | 24% |
  | Baseline B1, sequence k-NN | 60% |
  | Baseline B2, sequence DTW | 67% |
  | **Model C, 1D-CNN (shipped)** | **91%** |

  At the shipped threshold (0.62), the model answers 85% of vocab attempts and its answers are right 96% of the time.
- `python ml/recognizer.py` passes in the system Python (numpy only). It covers the original checks, the edge cases, a movement-only synthetic pair (the old baseline gets 0/8, sequence features get 8/8), and 15 reference clips (15/15).
- `train.py` is reproducible: a re-run with seed 0 gave bit-identical weights.
- Phase 4 is done: `reference.lookup("thirsty")` returns WATER's reference clip, `lookup("banana")` returns `None`, and the tests pass.

**What fell short / failed**
- **Precision missed its target on test.** I chose `MIN_CONFIDENCE` = 0.62 on validation for at least 90% precision, with non-vocab attempts weighted 1:1. On test that gives **87%**, because 9% of non-vocab signs get a vocab answer (for example TOY → PLAY and SORRY → LOVE). Validation had only 75 vocab clips. I did not re-tune on test. The test trade-off shows 0.80 would give about 93% precision at 77% coverage. **Raising it is your call.** Change `min_confidence` in `model.npz`, or add a `--target-precision` value and retrain.
- **ME is weak** (54% top-1; often read as LOVE). Both signs are made at the chest, and the model sees only one hand and no body.
- **Not measured:** per-signer accuracy (no signer IDs in public ASL Citizen mirrors), lighting, camera angle, children, our own webcams, and the live browser loop.
- Google ISLR (Kaggle) wasn't used because there were no credentials. pip needed `--use-feature=truststore` because AVG antivirus intercepts TLS.

**Review first**
1. `ml/README.md`, Task 5 and "Known limitations".
2. The decision about `MIN_CONFIDENCE` (0.62 shipped vs about 0.8; see the trade-off table).
3. The "Requested changes outside ml/" below. The 15-frame window and the hand switching in `Webcam.jsx` matter most.
4. Licenses: ASL Citizen is research-only and WLASL is C-UDA (academic). Fine for a hackathon demo, not for commercial use without review.

**Reproduce** (from the repo root, Windows paths):
```
python -m venv ml/.venv
ml/.venv/Scripts/python -m pip install --use-feature=truststore --upgrade pip
ml/.venv/Scripts/python -m pip install -r ml/requirements.txt --extra-index-url https://download.pytorch.org/whl/cpu
ml/.venv/Scripts/python ml/data_prep.py          # ~15 min
ml/.venv/Scripts/python ml/wlasl_prep.py         # ~6 min
ml/.venv/Scripts/python ml/train.py              # ~10 min, writes ml/model.npz + ml/results/
ml/.venv/Scripts/python ml/evaluate.py           # ~3 min, writes ml/results/accuracy_table.md
ml/.venv/Scripts/python ml/reference.py --build
python ml/recognizer.py && python ml/test_reference.py
```

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

### 2026-11-14 00:10 Phase 1: dataset search
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

### 2026-11-14 00:14 Phase 1: format checks and design decisions
- `.pose` stores x*width, y*height, raw z. `data_prep.py` divides back by width/height, so cached landmarks are exactly what MediaPipe JS returns in the browser (normalised image coords).
- Read (not edited) `frontend/src/components/Webcam.jsx` + `handTracker.js`: the browser sends `hands[0]` of each frame (can flip between left and right hand) in a rolling **15-frame window** (~0.25-0.5 s at display rate). A full sign is ~1-1.5 s. See "Requested changes outside ml/".
- `normalize()` puts the wrist at the origin per frame, which erases the hand's travel path. Kept `normalize()` unchanged and added 3 per-frame features computed the same way at train and inference time: wrist path relative to the clip's mean position, divided by median hand size (2), and log of hand size relative to its median (1, toward/away from camera). Still invariant to where the hand is and how big it is.
- Location relative to the body (chin vs chest) cannot be recovered: the browser sends no face/body landmarks.
- Training picks one hand per clip (the one detected in more frames). Mirror augmentation makes the model work for either hand; no vocab sign differs from another only by handedness, so mirroring is label-safe.
- Inference runs in **pure numpy** (`model.npz`) because `backend/requirements.txt` has no torch and I can't edit it. Torch is only needed for training.
- `recognizer.py` rewritten: same `normalize`, `load_templates`, `add_template`, `predict(frames, templates=None)`. Added input sanitising, hand-switch cleanup (`keep_one_hand`), `sequence_features`, numpy CNN inference, template fallback. Self-check extended (edge cases + movement-only pair: last-frame baseline 0/8, sequence features 8/8). Passes.
- `data_prep.py` started: 3432 clips (vocab + 86 negative glosses), 12 threads, resumable.
- `2026-11-14 00:20` [train.py] data: 1571 train / 435 val clips, 16 classes (257 / 75 are vocab signs)
- `2026-11-14 00:20` [train.py] A: last-frame NN (original): val closed-set acc 0.200; threshold 0.64 -> precision 0.500, coverage 0.013 (0s)
- `2026-11-14 00:20` [train.py] B1: sequence 5-NN: val closed-set acc 0.667; threshold 0.81 -> precision 1.000, coverage 0.027 (9s)
- `2026-11-14 00:21` [train.py] B2: sequence 1-NN DTW: val closed-set acc 0.787; threshold 0.50 -> precision 1.000, coverage 0.040 (42s)
- `2026-11-14 00:21` [train.py] Model C `small` {'width': 64, 'dilations': (1, 2), 'dropout': 0.2, 'lr': 0.002, 'weight_decay': 0.001}: best epoch 3/3, val_acc 0.427, val_loss 1.599, 4s
- `2026-11-14 00:21` [train.py] chosen config: `small` (val_acc 0.427)
- `2026-11-14 00:21` [train.py] WARNING: no threshold reached 90% validation precision; using the most precise one (0.95)
- `2026-11-14 00:21` [train.py] temperature 0.40 (val NLL 1.144); MIN_CONFIDENCE 0.95 -> val precision 0.500, coverage 0.027, false accepts on non-vocab 0.006
- `2026-11-14 00:21` [train.py] exported data\smoke_model.npz (238 KB); numpy vs torch max prob diff 5.66e-07
- `2026-11-14 00:21` [train.py] done; summary in results/train_summary.json

### 2026-11-14 00:21 Phase 1 done, Phase 2 started (section times before this were estimates; from here they come from the clock)
- data_prep.py finished: 3419 clips kept, 13 skipped (no hand detected in >=4 frames), 0 download errors. Per sign only ~28-61 clips (train 10-29, val 3-7, test 10-26): the HF repo's file count included anonymised duplicates. Details in `data_report.md`.
- Smoke test (3 epochs, output to data/smoke_model.npz) passed: numpy export matches torch (max prob diff 6e-7). Lines tagged [train.py] directly above/below with 'small ... best epoch 3/3' are from this smoke run.
- Decision: precision is computed with non-vocab clips re-weighted to equal the vocab clips in total (val has ~5x more non-vocab clips than vocab clips, which is far more 'random gesturing' than the Learn page produces). Unweighted and vocab-only precision are reported too.

- `2026-11-14 00:21` [train.py] data: 1571 train / 435 val clips, 16 classes (257 / 75 are vocab signs)
- `2026-11-14 00:21` [train.py] A: last-frame NN (original): val closed-set acc 0.200; threshold 0.64 -> precision 0.828, coverage 0.013 (0s)
- `2026-11-14 00:22` [train.py] B1: sequence 5-NN: val closed-set acc 0.667; threshold 0.81 -> precision 1.000, coverage 0.027 (9s)
- `2026-11-14 00:22` [train.py] B2: sequence 1-NN DTW: val closed-set acc 0.787; threshold 0.45 -> precision 0.918, coverage 0.093 (46s)
- `2026-11-14 00:24` [train.py] Model C `base` {'width': 96, 'dilations': (1, 2, 4), 'dropout': 0.3, 'lr': 0.002, 'weight_decay': 0.001}: best epoch 40/70, val_acc 0.933, val_loss 0.358, 121s
- `2026-11-14 00:26` [train.py] Model C `small` {'width': 64, 'dilations': (1, 2), 'dropout': 0.2, 'lr': 0.002, 'weight_decay': 0.001}: best epoch 18/48, val_acc 0.960, val_loss 0.671, 69s
- `2026-11-14 00:27` [train.py] Model C `wide` {'width': 128, 'dilations': (1, 2, 4), 'dropout': 0.4, 'lr': 0.0015, 'weight_decay': 0.003}: best epoch 21/51, val_acc 0.933, val_loss 0.583, 96s
- `2026-11-14 00:27` [train.py] chosen config: `small` (val_acc 0.960)
- `2026-11-14 00:27` [train.py] temperature 0.69 (val NLL 0.609); MIN_CONFIDENCE 0.72 -> val precision 0.908, coverage 0.800, false accepts on non-vocab 0.067
- `2026-11-14 00:27` [train.py] exported C:\Users\evan\Downloads\HackPrinceton\ml\model.npz (239 KB); numpy vs torch max prob diff 6.56e-07
- `2026-11-14 00:27` [train.py] done; summary in results/train_summary.json

### 2026-11-14 00:29 Run 1 (ASL Citizen only) result
- Lines above (00:21-00:27): Model C beats both baselines on validation (top-1 96% vs DTW 79% vs original last-frame 20%). Chosen config `small` (64 channels, dilations 1,2; 65k params, 239 KB file).
- Caveat: validation has only 75 vocab clips (3-7 per sign), so +-1 clip moves per-sign accuracy a lot and picking the best epoch on it is optimistic. The test split will tell.
- `python ml/recognizer.py` passes with the model, both in ml/.venv and in the system Python (numpy only, no torch): 15/15 reference clips, movement-only pair, edge cases.
- Added WLASL (Voxel51/WLASL on HF, C-UDA license, academic use only) as extra *training* data: `wlasl_prep.py` extracted 132 clips (5-14 per sign, 4-11 signers per sign) with MediaPipe HandLandmarker (same model as the browser), 0 skipped. Val/test stay ASL Citizen only. Next: run 2 = same sweep with WLASL added; pick between run 1 and run 2 on the same validation set.

- `2026-11-14 00:30` [train.py] data: 1703 train / 435 val clips, 16 classes (389 / 75 are vocab signs)
- `2026-11-14 00:30` [train.py] A: last-frame NN (original): val closed-set acc 0.187; threshold 0.64 -> precision 0.828, coverage 0.013 (0s)
- `2026-11-14 00:30` [train.py] B1: sequence 5-NN: val closed-set acc 0.653; threshold 0.81 -> precision 1.000, coverage 0.053 (10s)
- `2026-11-14 00:30` [train.py] B2: sequence 1-NN DTW: val closed-set acc 0.747; threshold 0.47 -> precision 0.923, coverage 0.067 (49s)
- `2026-11-14 00:34` [train.py] Model C `base` {'width': 96, 'dilations': (1, 2, 4), 'dropout': 0.3, 'lr': 0.002, 'weight_decay': 0.001}: best epoch 47/77, val_acc 0.947, val_loss 0.407, 189s
- `2026-11-14 00:36` [train.py] Model C `small` {'width': 64, 'dilations': (1, 2), 'dropout': 0.2, 'lr': 0.002, 'weight_decay': 0.001}: best epoch 51/81, val_acc 0.973, val_loss 0.473, 162s
- `2026-11-14 00:40` [train.py] Model C `wide` {'width': 128, 'dilations': (1, 2, 4), 'dropout': 0.4, 'lr': 0.0015, 'weight_decay': 0.003}: best epoch 54/84, val_acc 0.960, val_loss 0.300, 193s
- `2026-11-14 00:40` [train.py] chosen config: `small` (val_acc 0.973)
- `2026-11-14 00:40` [train.py] temperature 0.74 (val NLL 0.434); MIN_CONFIDENCE 0.62 -> val precision 0.902, coverage 0.880, false accepts on non-vocab 0.081
- `2026-11-14 00:40` [train.py] exported data\model_run2.npz (240 KB); numpy vs torch max prob diff 6.26e-07
- `2026-11-14 00:40` [train.py] done; summary in results/train_summary.json

### 2026-11-14 00:48 Run 2 chosen; single test evaluation
- Run 2 (ASL Citizen + WLASL train) lines above: baselines on val A 19%, B1 65%, B2 75% (WLASL slightly hurt the nearest-neighbour baselines: domain shift); Model C `small` val top-1 **97.3%** (run 1: 96.0%), val NLL 0.43 (run 1: 0.61), coverage at the 90%-precision threshold 88% (run 1: 80%). **Chose run 2** on validation; copied data/model_run2.npz -> model.npz. results/ and model_selfcheck.npz are from run 2.
- Calibration: temperature 0.74; **MIN_CONFIDENCE = 0.62** = smallest threshold with >= 90% validation precision (non-vocab clips weighted 1:1 with vocab clips) at that threshold and every higher one. Val coverage 88%, val false-accept on non-vocab 8%.
- Phase 4: `reference.py` (+ `references.npz`, 111 KB, medoid training clip per sign) and `test_reference.py`; all pass.
- **Test split, evaluated once** (`evaluate.py`; `results/accuracy_table.md`): Model C top-1 **91%** vs A 24% / B1 60% / B2 67%. At 0.62: coverage 85%, precision on vocab attempts 96%, weighted precision **87% (below the 90% target)**, 9% of non-vocab clips get a vocab answer. Short 15-frame windows: 87% top-1.
- I re-ran evaluate.py once more only to fix the per-sign precision column (it had mixed in the 5:1 non-vocab clips, making e.g. ALL-DONE look like 38%); same model, same threshold, same numbers otherwise. **The threshold was NOT changed after seeing test.** The test trade-off table shows 0.80 would give ~93% precision at 77% coverage; that is for a human to decide, flagged in the summary.
- Main errors: ME -> LOVE (5/13; both at the chest, location invisible with hand-only input); non-vocab near-twins TOY -> PLAY, DONT KNOW -> ALL-DONE, SORRY -> LOVE, HOME/OOPS -> EAT.
- `2026-11-14 00:48` [train.py] data: 1703 train / 435 val clips, 16 classes (389 / 75 are vocab signs)
- `2026-11-14 00:51` [train.py] Model C `small` {'width': 64, 'dilations': (1, 2), 'dropout': 0.2, 'lr': 0.002, 'weight_decay': 0.001}: best epoch 51/81, val_acc 0.973, val_loss 0.473, 146s
- `2026-11-14 00:51` [train.py] chosen config: `small` (val_acc 0.973)
- `2026-11-14 00:51` [train.py] temperature 0.74 (val NLL 0.434); MIN_CONFIDENCE 0.62 -> val precision 0.902, coverage 0.880, false accepts on non-vocab 0.081
- `2026-11-14 00:51` [train.py] exported data\repro.npz (240 KB); numpy vs torch max prob diff 6.26e-07
- `2026-11-14 00:51` [train.py] done; summary in results/train_summary.json

### 2026-11-14 00:52 Reproducibility check and Phase 5
- Re-ran `train.py --configs small --no-baselines --out data/repro.npz` (seed 0): same best epoch (51), val acc 0.973, temperature 0.74, threshold 0.62; weights **bit-identical** to model.npz. The re-run overwrote results/train_summary.json, results/history_small.csv and model_selfcheck.npz with single-config versions; restored them from the last commit with `git checkout -- <those files>` (working-tree restore only, no history change). The 'Model C small ... 146s' / 'chosen config' / 'exported data\repro.npz' lines right above are from this check.
- Inference speed: ~4 ms per `predict()` (15 or 60 frames), system Python + numpy.
- Wrote `ml/README.md` (kept original content; added status, how it works, Task 5 table, model comparison, coverage trade-off, variants, known limitations) and the summary at the top of this log.
