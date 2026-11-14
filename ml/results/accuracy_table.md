Split: **test** (233 clips of vocab signs, 1180 clips of other signs). Model threshold MIN_CONFIDENCE = 0.62 (chosen on validation).

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

Overall precision when it answers, with non-vocab attempts weighted to equal vocab attempts (1:1): **87%** (validation target was 90%). Unweighted, with all 1180 non-vocab clips at their real 5:1 ratio: 63%. Non-vocab clips that got a (wrong) vocab answer: 9%.

**Model comparison (same test clips; each at its own validation-chosen threshold):**

| Model | Top-1 accuracy | Precision when it answers | Coverage | Non-vocab clips wrongly answered |
|---|---:|---:|---:|---:|
| A: last-frame NN (original) | 24% | 54% | 3% | 1% |
| B1: sequence 5-NN | 60% | 94% | 9% | 0% |
| B2: sequence 1-NN DTW | 67% | 86% | 9% | 0% |
| **C: 1D-CNN sequence model (chosen)** | **91%** | **87%** | **85%** | **9%** |

**Short browser-like windows** (middle 15 frames of each clip, like `Webcam.jsx` sends today): Model C accuracy 87%, precision 86%, coverage 83%; Baseline A accuracy 39%.

**Coverage vs precision (Model C, test):**

| Threshold | Precision | Coverage | Non-vocab wrongly answered |
|---:|---:|---:|---:|
| 0.00 | 81% | 94% | 15% |
| 0.30 | 81% | 94% | 15% |
| 0.40 | 82% | 93% | 14% |
| 0.50 | 85% | 91% | 12% |
| 0.60 | 87% | 86% | 9% |
| 0.70 | 89% | 82% | 7% |
| 0.80 | 93% | 77% | 4% |
| 0.90 | 95% | 67% | 3% |
| 0.95 | 97% | 58% | 2% |

**Most frequent confusions (true -> predicted, top-1, test):** ME -> LOVE (5), HELP -> WHAT (2), WHAT -> WANT (2), ALL-DONE -> WHAT (1), LOVE -> EAT (1), ME -> YES (1), MILK -> EAT (1), SLEEP -> WANT (1), SLEEP -> MILK (1), WANT -> ALL-DONE (1)

**Non-vocab signs most often answered as a vocab sign (test, at the threshold):** TOY 1 -> PLAY (10), DONT KNOW -> ALL-DONE (9), SORRY -> LOVE (6), VANILLA -> NO (6), NOT USED_TO -> ALL-DONE (4), HOME -> EAT (3), OOPS -> EAT (3), RAKE -> WHAT (3), TOY 3 -> PLAY (3), ANALYZE -> NO (2), DRUNK -> YES (2), HABIT -> YES (2), HAMSTER -> NO (2), JELLY -> HELP (2), JELLY -> WHAT (2)
