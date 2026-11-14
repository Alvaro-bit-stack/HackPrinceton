# ml: sign recognition (Person 1)

Turns the child's signing into a word. The camera runs in the browser, so your work spans two files:

| File | What it does |
|---|---|
| `ml/recognizer.py` | `predict(frames)` returns `{sign, confidence}`. The backend calls this. |
| `frontend/src/lib/handTracker.js` | Runs MediaPipe in the browser and yields hand landmarks. |

Nobody else edits these two files, and you don't need to edit anything else.

## Tasks
1. Get `handTracker.js` logging 21 landmarks per hand from the webcam.
2. Record templates for two signs (`add_template`) and check `predict` tells them apart.
3. Pick the first 10 signs from `shared/vocab.json` that differ by handshape and record them with all three teammates.
4. Find a dataset or pretrained model for signs that differ by movement, and replace the baseline.
5. Measure accuracy: for each sign, how often is it right across people and lighting? Put the table here.

Status after the overnight run (branch `overnight-sign-model`, details in `OVERNIGHT_LOG.md`):
- **Task 1:** not touched (out of scope).
- **Tasks 2 and 3:** no team recordings exist yet. The template path still works (`add_template` / `templates.json`), and the model was trained on public data for all 15 vocab signs instead.
- **Task 4:** done. A small 1D-CNN reads the whole frame sequence. It was trained on ASL Citizen and WLASL hand landmarks and is described below.
- **Task 5:** the table is below. It measures *adult* signers from public datasets. Our own people, children, and lighting were not measured.

## Run
```
pip install numpy
python ml/recognizer.py     # self-check (numpy only; uses ml/model.npz)
python ml/test_reference.py # English -> reference sign lookup tests
```

Training and evaluation use the virtual environment in `ml/.venv`. Install it once, then run the scripts in order:
```
python -m venv ml/.venv
ml/.venv/Scripts/python -m pip install -r ml/requirements.txt --extra-index-url https://download.pytorch.org/whl/cpu
ml/.venv/Scripts/python ml/data_prep.py        # ASL Citizen landmarks -> ml/data/landmarks (~15 min, resumable)
ml/.venv/Scripts/python ml/wlasl_prep.py       # + WLASL clips of the vocab signs (~6 min, resumable)
ml/.venv/Scripts/python ml/train.py            # baselines + model sweep -> ml/model.npz (~10 min on CPU, seed 0)
ml/.venv/Scripts/python ml/evaluate.py         # test table -> ml/results/accuracy_table.md
ml/.venv/Scripts/python ml/reference.py --build  # -> ml/references.npz
```
Behind a TLS-inspecting antivirus or proxy, upgrade pip first with `pip install --use-feature=truststore --upgrade pip`.

## Notes
- The baseline reads handshape from one frame. It cannot tell apart signs that differ only by movement or location.
- Output goes to parents as a hint, never as "correct" or "wrong". Keep `MIN_CONFIDENCE` high enough that wrong guesses are rare.

## How the recognizer works now

`predict(frames, templates=None)` keeps the same signature and output.
1. **Input cleanup.** Malformed, NaN, or inf frames are treated as missing. If the browser's `hands[0]` flips between the two hands, `keep_one_hand` keeps one wrist track. Fewer than 4 usable frames, empty input, or bad shapes return `{"sign": None, "confidence": 0.0}`. `predict()` never raises.
2. **Features** (`sequence_features`, shared with training). Each frame gets `normalize()` (unchanged: wrist at origin, scaled by wrist-to-middle-knuckle). Two extra things are added that `normalize()` throws away, both still independent of where the hand is and how big it is:
   - the wrist's path relative to the clip's mean position, in hand-size units;
   - the hand's apparent size over time.

   The detected span is resampled to 32 steps, and frame-to-frame velocities are appended, giving 132 numbers per step.
3. **Model.** Two dilated Conv1d layers (64 channels), mean and max pooling over time, then a linear layer over 15 signs plus a "not a vocab sign" class. That's 65k parameters in `model.npz` (240 KB), run in **pure numpy** (about 4 ms per call on CPU), so the backend doesn't need torch.
4. **Confidence.** A softmax with a temperature fitted on validation (0.74). The answer is `None` if the model says "not a vocab sign" or if confidence is below **`min_confidence` = 0.62**. That threshold is stored in `model.npz` and chosen on validation as the lowest threshold whose precision is at least 90% there.
5. **Fallbacks.** If `model.npz` is missing, or the caller passes `templates=...`, `predict()` uses the original last-frame nearest-neighbour (`MIN_CONFIDENCE = 0.6`).

To train on your own recordings, save each attempt as `ml/data/landmarks/<GLOSS>/<signer>__<name>.npy`, a float array of shape (T, 21, 3) holding raw MediaPipe landmarks for one hand, with NaN rows where no hand was seen. Then run `train.py`. Folders not named after a vocab gloss count as "not a vocab sign". See `ml/dataset.py` and `ml/data_report.md`.

`ml/reference.py`: `lookup("thirsty")` returns WATER's reference landmark sequence, a real training clip (the medoid), plus metadata. It returns `None` for words outside the vocab. This is retrieval only.

## Task 5: accuracy

**Data:**
- **Test set:** the official ASL Citizen test split. Its signers do not appear in training (the split is signer-disjoint).
- **Clips:** 233 clips of the 15 vocab signs (10–26 per sign), plus 1,180 clips of 86 other signs that should get no answer.
- **Training data:** ASL Citizen train and validation splits, plus WLASL.
- **Evaluation runs:** the test set was evaluated once, after the model and threshold were chosen on validation. A second run only fixed how per-sign precision was displayed.
- **Source:** `ml/results/accuracy_table.md` and `ml/results/test_results.json` (regenerate with `evaluate.py`).

Column definitions:
- **Accuracy:** top-1 accuracy, ignoring the threshold.
- **Coverage:** the share of attempts that got an answer.
- **Answered and right:** the share of attempts that got the correct answer.
- **Precision on vocab attempts:** when someone signs a vocab sign and the model answers, how often the answer is right.
- **Baseline A:** the original last-frame nearest-neighbour, with every training clip's last frame as a template.

| Sign | Test clips | Accuracy (top-1) | Coverage (answers given) | Answered and right | Precision on vocab attempts | Non-vocab clips answered as this sign | Baseline A accuracy |
|---|---:|---:|---:|---:|---:|---:|---:|
| ALL-DONE | 14 | 93% | 86% | 86% | 100% (12) | 20 | 29% |
| EAT | 26 | 100% | 100% | 100% | 96% (27) | 8 | 46% |
| HELP | 13 | 85% | 77% | 77% | 91% (11) | 3 | 23% |
| LOVE | 12 | 92% | 83% | 83% | 71% (14) | 10 | 25% |
| ME | 13 | 54% | 77% | 46% | 100% (6) | 2 | 15% |
| MILK | 23 | 96% | 83% | 78% | 100% (18) | 2 | 26% |
| MORE | 12 | 100% | 100% | 100% | 100% (12) | 3 | 33% |
| NO | 11 | 100% | 100% | 100% | 100% (11) | 10 | 27% |
| PLAY | 14 | 100% | 93% | 93% | 100% (13) | 16 | 14% |
| SLEEP | 12 | 83% | 67% | 67% | 100% (8) | 0 | 8% |
| WANT | 24 | 92% | 79% | 79% | 90% (21) | 0 | 12% |
| WATER | 12 | 100% | 92% | 92% | 100% (11) | 4 | 33% |
| WHAT | 25 | 80% | 76% | 64% | 100% (16) | 9 | 20% |
| YES | 10 | 100% | 100% | 100% | 100% (10) | 7 | 20% |
| YOU | 12 | 100% | 75% | 75% | 100% (9) | 8 | 17% |
| **All signs** | 233 | **91%** | 85% | 82% | 96% | 102 of 1180 | 24% |

**Precision at the chosen threshold (0.62):**
- When someone signs one of the 15 vocab signs and the model answers, it's right **96%** of the time.
- The validation target was 90% precision with non-vocab attempts weighted equally to vocab attempts (1:1). On test, that weighted precision is **87%, below the target.** The shortfall comes from 9% of non-vocab signs getting a vocab answer.
- If non-vocab signs are counted at their real 5:1 ratio in this test set, precision is 63%. On the Learn page, the child is attempting the shown sign, so the vocab-attempt numbers are the more relevant ones there.

**Model comparison** (same test clips; each model at its own validation-chosen threshold):

| Model | Top-1 accuracy | Precision when it answers (1:1 weighting) | Coverage | Non-vocab clips wrongly answered |
|---|---:|---:|---:|---:|
| A: last-frame NN (original) | 24% | 54% | 3% | 1% |
| B1: sequence 5-NN | 60% | 94% | 9% | 0% |
| B2: sequence 1-NN DTW | 67% | 86% | 9% | 0% |
| **C: 1D-CNN sequence model (chosen)** | **91%** | **87%** | **85%** | **9%** |

The baselines reach their precision only by almost never answering (3–9% coverage).

**Coverage vs precision for Model C** (test; 1:1 weighting). This table is for information only. The shipped threshold was chosen on validation, not from this table.

| Threshold | Precision | Coverage | Non-vocab wrongly answered |
|---:|---:|---:|---:|
| 0.50 | 85% | 91% | 12% |
| **0.62 (shipped)** | **87%** | **85%** | **9%** |
| 0.70 | 89% | 82% | 7% |
| 0.80 | 93% | 77% | 4% |
| 0.90 | 95% | 67% | 3% |

**Short windows:** `Webcam.jsx` sends 15 frames. Scored on only the middle 15 frames of each clip, Model C gets 87% top-1, 86% precision, and 83% coverage. Baseline A gets 39%.

**Across signers, lighting, and cameras:**
- **Signers:** test signers are all unseen, but ASL Citizen doesn't publish per-clip signer IDs, so **per-signer accuracy couldn't be computed.**
- **Lighting and camera:** ASL Citizen clips come from home webcams with varied lighting, but none of it is labeled, so **accuracy by lighting or camera angle couldn't be measured.**
- **Our own team** hasn't been recorded yet.

**Sign variants** (test top-1):

| Variant | Correct |
|---|---:|
| MILK | 10/11 |
| MILK 2 | 12/12 |
| EAT | 17/17 |
| EAT 2 | 9/9 |
| WANT | 12/12 |
| WANT 2 | 10/12 |
| WHAT 1 | 10/12 |
| WHAT 2 | 10/13 |

## Known limitations

- **Thin data.** Each sign has 10–29 training clips from ASL Citizen plus 4–14 from WLASL. Validation has only 3–7 clips per sign, so the threshold was chosen on just 75 vocab clips and missed its target on test by 3 points. Per-sign numbers above rest on 10–26 test clips, so a single clip moves a row by 4–10 points.
- **Confusions** (true sign → predicted sign):
  - Within the vocab: ME → LOVE (5 of 13 ME clips; both are made at the chest), HELP → WHAT, WHAT → WANT.
  - Non-vocab signs answered as vocab: TOY → PLAY, DONT KNOW → ALL-DONE, SORRY → LOVE, HOME/OOPS → EAT, VANILLA → NO.

  These pairs differ mostly by *where* the hand is relative to the body or face, by the second hand, or by facial expression.
- **One hand, no body.** The browser sends one hand's 21 points, with no face, body, or second hand. Location (chin vs chest) and two-handed contrasts are invisible to the model. MORE, HELP, ALL-DONE, PLAY, and LOVE are two-handed signs, and the model sees only one hand of each.
- **Signer diversity.** ASL Citizen has 52 adult signers in total; WLASL adds 32 in training. **No children.** Children's hands are smaller and their signing is less precise. Normalization handles size, but not imprecise handshapes or movements. This has not been tested at all.
- **Not tested:**
  - our own webcams and the live browser pipeline end to end;
  - children;
  - lighting, camera angle, and distance;
  - left-handed signers specifically (mirror augmentation was used, but there's no labeled test);
  - the 15-frame window at the browser's real frame rate (up to 60 fps, so 0.25 s).
- **Licenses.** ASL Citizen is research-only and WLASL is C-UDA (academic use only), so commercial use needs a review.
- The frontend changes that would help most (a longer window and a consistent hand) are listed under "Requested changes outside ml/" in `OVERNIGHT_LOG.md`.
