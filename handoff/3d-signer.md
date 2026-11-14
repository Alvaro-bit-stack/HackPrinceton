# Handoff: 3D signer and camera changes for the new backend

**For:** Person 1 (signer / ML), and any AI assistant helping them.
**From:** Person 3 (backend).
**Source of truth for request and response shapes:** [`CONTRACT.md`](../CONTRACT.md). If this file and the contract disagree, the contract wins.

## Summary
You own two things the backend now depends on:

1. **The signer** (`frontend/src/components/SignPlayer.jsx`). It gets three inputs from every translation: `signs`, `face` and `emotion`. It must show the signs in order, set the eyebrows from `face`, and set the rest of the face and the size of the movement from `emotion`.
2. **The face camera** (new file `frontend/src/lib/faceEmotion.js`). It reads the parent's emotion while they speak and returns seven scores that the frontend sends to the backend.

Plus one rule that ties the two together: **`shared/vocab.json` may only list signs that have an animation clip.** The backend only ever chooses signs from that file.

## Part 1: what the signer receives
Every translation, from the Speak page or a Storybook page, gives you:

```json
{
  "signs": [{"gloss": "MILK", "known": true}, {"gloss": "PIZZA", "known": false}],
  "face": "yes-no-question",
  "emotion": "happy"
}
```

The frontend passes these to `<SignPlayer signs face emotion />`. The response also has `meaning`, `source` and `unsure`; the frontend shows those as text, and they don't change the signing.

### 1a. Signs
- **Order:** play them in the order given. It is already ASL order, not English order.
- **`known: true`:** play the clip whose name is exactly the gloss, such as `MILK`.
- **`known: false`:** there is no sign, so fingerspell the gloss letter by letter (P-I-Z-Z-A). This needs one handshape clip per letter, A to Z. The gloss can contain apostrophes, hyphens or digits (`PIP'S`), so skip anything that isn't a letter. Until the letter clips exist, show the word as text on screen while the signer pauses.
- **Gloss names:** capitals, with a hyphen for multi-word signs, such as `ALL-DONE`. Name clips the same way.

### 1b. `face` sets the eyebrows (grammar)
In ASL the eyebrows are grammar: they turn a sentence into a question. Hold the shape for the whole sentence.

| `face` | Eyebrows | Shape keys on our models | Head |
|---|---|---|---|
| `statement` | Taken from the emotion (1c) | none | Neutral |
| `yes-no-question` | Raised | `browInnerUp` 1.0, `browOuterUpLeft` 1.0, `browOuterUpRight` 1.0 | Tilt slightly forward |
| `wh-question` | Lowered, drawn together | `browDownLeft` 1.0, `browDownRight` 1.0 | Tilt slightly forward |

### 1c. `emotion` sets the rest of the face and the movement
Starting values below. Tune them by eye, and have a fluent signer check them.

| `emotion` | Face (shape keys) | Movement speed | Movement size |
|---|---|---|---|
| `neutral` | none | 1.0× | 1.0× |
| `happy` | `mouthSmileLeft` 0.7, `mouthSmileRight` 0.7 | 1.0× | 1.1× |
| `sad` | `mouthFrownLeft` 0.6, `mouthFrownRight` 0.6, `browInnerUp` 0.5 | 0.85× | 0.9× |
| `angry` | `browDownLeft` 0.8, `browDownRight` 0.8, `mouthFrownLeft` 0.3, `mouthFrownRight` 0.3 | 1.15× | 1.1× |
| `surprised` | `browInnerUp` 0.8, `browOuterUpLeft` 0.8, `browOuterUpRight` 0.8, `eyeWideLeft` 0.7, `eyeWideRight` 0.7, `jawOpen` 0.25 | 1.1× | 1.15× |
| `worried` | `browInnerUp` 0.7, `mouthFrownLeft` 0.3, `mouthFrownRight` 0.3, `eyeWideLeft` 0.3, `eyeWideRight` 0.3 | 0.9× | 0.95× |

**When grammar and emotion both want the eyebrows:** if `face` is a question, the grammar eyebrows win and the emotion keeps only its mouth and eyes. An angry question has lowered or raised brows from the grammar plus a frown from the emotion. If `face` is `statement`, the emotion sets the eyebrows too.

**Which model can show this:**
- **`pip.glb`** has all the shape keys above.
- **`signer.glb`** (the Meshy character) has only the five brow keys. Its eyebrows work, but mouth and eye emotion won't show until those keys are added.

### 1d. Blending
Ease into each new face over about 150 ms rather than snapping. Keep it for the whole sentence, and return to neutral after the last sign.

## Part 2: the face camera (`frontend/src/lib/faceEmotion.js`)
**Why:** the backend weighs the parent's face alongside their words to decide the emotion and what they mean. "You ate all of it" with a smile is praise; with raised brows it's surprise.

**Library:** `@vladmandic/face-api`, the maintained fork of face-api.js. Load its face detector and expression model.

**What to build:** two functions the frontend calls around speech recognition.

```js
// Starts sampling the webcam about 5 times a second. Call when the parent starts speaking.
export async function startFaceEmotion(videoElement) {}

// Stops sampling. Returns the average score per expression over the frames where a face
// was found, or null if a face was seen in fewer than half the frames.
// Shape: { neutral, happy, sad, angry, fearful, disgusted, surprised }, each 0 to 1.
export function stopFaceEmotion() {}
```

**Rules:**
- **Key names:** use exactly these seven, because the backend rejects any other: `neutral`, `happy`, `sad`, `angry`, `fearful`, `disgusted`, `surprised`.
- **Values:** numbers from 0 to 1.
- **Privacy:** process everything in the browser. Never send video or images to the backend; only the seven numbers leave the device.
- **No face, no scores:** return `null` when no face was found in at least half the frames. The frontend then sends nothing.
- **Known limit:** glasses lower the model's accuracy. The backend lets the words outrank the face, so a bad reading does limited harm.

**How the backend uses the scores:**
- **On the model path:** the language model sees them and weighs them against the words.
- **On a phrase-bank match, and in fallback mode:** an emotion scoring 0.6 or more replaces the default. Fearful counts as worried, and disgusted adds to angry.
- **Neutral never overrides anything,** because a concentrating parent often reads as neutral.

### Stretch: eyebrow coaching
On a question, check whether the parent's own eyebrows went up and prompt them if not. This uses MediaPipe's `browInnerUp` measurement, runs only in the browser, and never touches the backend. Only do it once Parts 1 and 2 work.

## Part 3: the vocabulary rule
The backend reads `shared/vocab.json` at startup and only ever returns glosses from it, plus `known: false` words to fingerspell.

- **Only signs with a clip:** if a gloss is in the file but has no clip, the signer can't show it.
- **What to animate next:** [`shared/next_signs.md`](../shared/next_signs.md) lists 517 signs from the ASL children's vocabulary checklist that we don't have yet, earliest-learned first. Each row gives the ASL-LEX handshape and location to check your clip against. Start at the top. `GET /progress` also lists, under `catch_up.not_yet_animated`, the early signs real families are missing, which is a good tie-breaker.
- **Adding a sign:** record or capture the clip, then add `{"gloss": "BALL", "english": ["ball"], "asl_lex": "ball"}` to `vocab.json`, using the entry name from `next_signs.md` as `asl_lex`. Tell Person 3 and restart the backend. List every English word that should map to the sign, such as `"english": ["eat", "food", "hungry"]`.
- **Removing a sign:** take it out of `vocab.json` too.
- **Credit:** ASL-LEX is CC BY-NC, so its credit line stays in `next_signs.md` and the README. Its iconicity ratings, in `shared/asl_lex.json`, are a good teaching order for the Practice page.

## Part 4: one avatar per family member
The parent picks who is talking, so the child sees a signer that looks like that parent (for example "Mom" and "Dad" versions of Pip).

- `SignPlayer` gets a new prop, `avatar`: a short id such as `pip-mom`, or `null`/`undefined` for the default signer (the backend sends `null` when a member has no avatar). Load `frontend/public/models/<avatar>.glb` and fall back to the default if the file is missing.
- **Every avatar uses the same skeleton (bone names) and the same face shape keys.** Then every clip and every face/emotion setting plays on any avatar with no extra work. Change the look (hair, colours, glasses), not the rig.
- Tell Person 2 the list of avatar ids so the settings screen can offer them. The backend stores the chosen id per family member and doesn't check it.
- Two avatars are enough for the demo.

## The T-shirt signer (`signer_tshirt.glb`)
A kid in a plain T-shirt, ready for three.js:
- **Skeleton:** 43 bones, including every finger joint (`RightIndexProximal`…), the same names as `pip.glb`.
- **Face:** 20 morph targets with the names in Part 1 (`browInnerUp`, `browDownLeft`, `jawOpen`, `mouthPucker`, `mouthFunnel`, `mouthSmileLeft`, `eyeBlinkLeft`…). The closed mouth shows as a thin dark lip line.
- **One clip, `YOU_WANT_MORE_MILK`** (126 frames at 24 fps): YOU, WANT, MORE, MILK with English mouthing and raised question brows. It's a whole sentence, a sample of quality, not per-sign clips yet.
- Made in Blender by hand, not from motion capture: have a fluent signer check it.

## The glasses signer (`signer_glasses.glb`)
A kid with glasses and a blue T-shirt, built from a Meshy T-pose model (about 25k triangles, 5.8 MB, JPEG textures):
- **Skeleton and face:** the same 43 bone names and the same 20 morph targets as `signer_tshirt.glb`, so clips and face settings carry over. The rest pose is a T-pose, not arms-down, so a clip made on another avatar needs its arm rotations redone.
- **Hands:** the arms are the model's own; the hands are replaced from the wrist with five-finger hands in a flat skin colour.
- **Face:** eyelids sit behind the glasses. Smile and frown bend a painted lip line, so they stay modest.
- **One clip, `YOU_WANT_MILK`** (100 frames at 24 fps): YOU, WANT, MILK with English mouthing, raised question brows and a forward head tilt, right hand dominant.
- Made in Blender by hand, not from motion capture: have a fluent signer check it.

## Who owns what
| File | Owner |
|---|---|
| `frontend/src/components/SignPlayer.jsx` | You |
| `frontend/public/models/` (`pip.glb`, `signer.glb`, `signer_tshirt.glb`, `signer_glasses.glb`, clips) | You |
| `frontend/src/lib/faceEmotion.js` (new) | You |
| `shared/vocab.json` | Shared: you add signs, and tell Person 3 |
| `frontend/src/pages/*` | Person 2, who calls your functions and passes your props |
| `backend/*` | Person 3 |

## Checklist
- [ ] `SignPlayer` plays clips in order and fingerspells, or shows text for, `known: false`.
- [ ] Eyebrows follow `face`, with the grammar eyebrows winning on questions.
- [ ] Face and movement follow `emotion`, using the table as a starting point.
- [ ] `faceEmotion.js` exports `startFaceEmotion` and `stopFaceEmotion`, returns the seven keys or `null`, and never sends video.
- [ ] `vocab.json` lists only signs that have a clip.
- [ ] `SignPlayer` takes an `avatar` prop; at least two avatars share one skeleton and one set of shape keys.
