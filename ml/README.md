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

## Run
```
pip install numpy
python ml/recognizer.py     # self-check
```

## Notes
- The baseline reads handshape from one frame. It cannot tell apart signs that differ only by movement or location.
- Output goes to parents as a hint, never as "correct" or "wrong". Keep `MIN_CONFIDENCE` high enough that wrong guesses are rare.
