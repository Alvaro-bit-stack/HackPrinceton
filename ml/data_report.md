# Data report

Generated during the overnight run (2026-11-14). Regenerate the data with `ml/data_prep.py` then `ml/wlasl_prep.py`.

## Sources

| Source | What | Used for | License |
|---|---|---|---|
| [ASL Citizen](https://www.microsoft.com/en-us/research/project/asl-citizen/) via [`SorensenAI/asl-citizen-poses`](https://huggingface.co/datasets/SorensenAI/asl-citizen-poses) | MediaPipe Holistic landmarks, one `.pose` file per clip. 52 Deaf/hard-of-hearing signers recorded on their own webcams. | train / val / test | Microsoft research dataset license (non-commercial research) |
| Official ASL Citizen splits via [`mage0001/ASLCitizen-3D`](https://huggingface.co/datasets/mage0001/ASLCitizen-3D) `samples.csv` | train/val/test per clip | the split | as above |
| [WLASL](https://github.com/dxli94/WLASL) via [`Voxel51/WLASL`](https://huggingface.co/datasets/Voxel51/WLASL) | Videos (mostly 320x240). Hand landmarks extracted here with MediaPipe HandLandmarker, the same model the browser runs. | **train only** | C-UDA (academic/computational use only) |

**Neither license allows commercial use. Check before shipping anything beyond a hackathon demo.**

Not used:
- **Google ISLR (Kaggle "asl-signs"):** needs a Kaggle login and acceptance of the competition rules, and there were no credentials on this machine. It also covers only about 7 of the 15 vocab signs.
- **The rest of WLASL:** only the 132 clips of vocab signs were needed.

## Split (no leakage)

- **ASL Citizen:** the dataset's own train/val/test split, which the ASL Citizen paper defines as **signer-disjoint**. No signer in validation or test appears in training. Public mirrors don't include per-clip participant IDs, so the split is by signer but per-signer numbers can't be reported.
- **WLASL** clips (32 signers) go to **training only**, so validation and test are pure ASL Citizen and stay comparable across runs. WLASL and ASL Citizen are separate collections. Some people may appear in both, but that can't be checked.
- 13 clips (3 vocab, 10 non-vocab) were dropped because a hand was detected in fewer than 4 frames.

## Vocab signs (positives)

| Sign | ASL Citizen source glosses | train (ASL Citizen) | train (WLASL) | val | test | skipped (no hand) | WLASL signers | median frames with a hand |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| MILK | MILK, MILK 2 | 29 | 5 | 7 | 23 | 0 | 5 | 32 |
| MORE | MORE | 14 | 8 | 4 | 12 | 0 | 7 | 31 |
| EAT | EAT, EAT 2 | 28 | 7 | 7 | 26 | 0 | 7 | 25 |
| WATER | WATER | 13 | 9 | 4 | 12 | 0 | 8 | 29 |
| SLEEP | SLEEP | 11 | 6 | 5 | 12 | 1 | 6 | 26 |
| HELP | HELP | 12 | 14 | 5 | 13 | 0 | 9 | 35 |
| ALL-DONE | FINISH | 14 | 9 | 3 | 14 | 0 | 8 | 26 |
| WANT | WANT, WANT 2 | 29 | 9 | 7 | 24 | 0 | 8 | 28 |
| YOU | YOU | 14 | 8 | 4 | 12 | 0 | 7 | 23 |
| ME | ME | 10 | 4 | 5 | 13 | 2 | 4 | 23 |
| LOVE | LOVE | 12 | 7 | 5 | 12 | 0 | 5 | 33 |
| WHAT | WHAT 1, WHAT 2 | 29 | 12 | 7 | 25 | 0 | 11 | 28 |
| YES | YES | 14 | 12 | 5 | 10 | 0 | 10 | 29 |
| NO | NO | 15 | 11 | 3 | 11 | 0 | 10 | 31 |
| PLAY | PLAY | 13 | 11 | 4 | 14 | 0 | 9 | 28 |
| **Total** | | **257** | **132** | **75** | **233** | **3** | 32 total | |

Decisions:
- **`ALL-DONE` = ASL Citizen `FINISH`.** "All done" is signed as FINISH.
- **Sign variants are merged under one label:** MILK/MILK 2, EAT/EAT 2, WANT/WANT 2, WHAT 1/WHAT 2. A child might use either form. Signs with two variants therefore have about twice the clips.
- **No vocab class was dropped.** All 15 signs have at least 10 training clips from ASL Citizen.
- **This is thin data:** 10–29 ASL Citizen training clips per sign, plus 4–14 from WLASL. Validation has only 3–7 clips per sign, so per-sign validation numbers are very noisy.

## Non-vocab signs (negatives, class `_OTHER`)

There are 86 ASL Citizen glosses: train 1,314 clips, val 360, test 1,180 (same official split). They teach the model to answer "none of these" and are used to measure false answers.
- **16 hard negatives,** whose English overlaps the vocab or which look similar: HUNGRY, THIRSTY, TIRED, BED, DRINK, PLEASE, THANK YOU, MOTHER, FATHER, GOOD, BATHROOM, HOME, NAME, SORRY, WHERE, WHO.
- **70 random other glosses** (seed 0), for example TOY, NEED, OK, YAY, DONT KNOW. TOY is close to PLAY, which makes it a useful hard case.

## Format of the cached data (also what new recordings should look like)

`ml/data/landmarks/<GLOSS>/<clip>.npy` holds a float array of shape (T, 21, 3): one hand per frame, as raw MediaPipe output.
- x and y are normalized image coordinates and z is MediaPipe's relative depth.
- A frame with no hand is a row of NaN or all zeros.
- A file can include a signer ID as a filename prefix, for example `evan__milk_03.npy`.

`ml/data/landmarks/splits.csv` (columns `path,gloss,split,signer,...`) is optional. Without it, clips are split by signer prefix 70/15/15. See `ml/dataset.py`.

## Recording conditions

ASL Citizen clips are webcam recordings by adult signers at home, so lighting, backgrounds, and cameras vary but aren't labeled. WLASL is mostly studio or online-dictionary video. **There are no children in either dataset,** and there are no lighting or camera-angle labels.
