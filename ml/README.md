# Signer and ML (Person 1)

You own the signing itself: given an ordered list of signs, a grammar face and an emotion, show a signer performing them.

| File | What it does |
|---|---|
| `frontend/src/components/SignPlayer.jsx` | Takes `signs`, `face` and `emotion` and shows the signing. Currently words on cards. |
| `frontend/public/models/` | The 3D signer (`signer.glb`) and any sign clips. |
| `ml/` | Scripts for capturing sign motion, plus the stretch recogniser. |

Nobody else edits these.

## Tasks
1. Load `signer.glb` in `SignPlayer.jsx` with three.js and play its built-in demo animation.
2. Build the sign library: one motion per gloss in `shared/vocab.json`. Capture each from a video of a real signer with MediaPipe and save the joint rotations.
3. Play a sign list in order, blending the end of one sign into the start of the next.
4. Drive the face from the `face` tag: raised brows for `yes-no-question`, lowered for `wh-question`. The model already has these brow controls.
5. Show the `emotion` tag on the signer: the rest of the face, and how large or sharp the movement is. Keep it separate from the eyebrow grammar in task 4, since an angry question needs both.
6. Handle `known: false` words: fingerspell them, or show the word as text if the alphabet isn't ready.
7. Before the hour-16 check-in, report how many glosses have a motion. That number drives the pivot decision.

## Fallback
If driving the 3D signer stalls, play one short video clip per sign instead. The rest of the app doesn't change, because `SignPlayer` takes the same inputs.

## Stretch: recognising the child's signs
`ml/recognizer.py` and `frontend/src/lib/handTracker.js` read signs from the camera for the Practice page. They are a working starter. Leave them until the main goal or the pivot demos cleanly.

```
pip install numpy
python ml/recognizer.py     # self-check
```
