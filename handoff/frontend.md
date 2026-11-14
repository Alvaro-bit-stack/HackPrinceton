# Handoff: frontend changes for the new backend

**For:** Person 2 (frontend), and any AI assistant helping them.
**From:** Person 3 (backend).
**Source of truth for request and response shapes:** [`CONTRACT.md`](../CONTRACT.md). If this file and the contract disagree, the contract wins.

## Summary
The backend now translates with a language model, double-checks every translation, reads the parent's emotion, and accepts corrections from the parent. The frontend needs five changes:

1. Send two new optional fields to `/translate`.
2. Show a loading state, because a translation can take several seconds.
3. Show what the backend understood (`meaning`) and how much to trust it (`source`, `unsure`).
4. Let the parent correct the meaning or emotion with one tap, using the new `POST /corrections`.
5. Pass the parent's face emotion scores when the camera is on.

Nothing else in the frontend has to change. The Storybook page works as it is and gains the same new fields.

## What changed in the backend
- **Request:** `/translate` accepts `emotion` (optional) and `face_emotions` (optional) next to `text`.
- **Response:** `/translate` returns three new fields: `meaning`, `source` and `unsure`. The old `checked` field is gone; nothing in the frontend used it.
- **New route:** `POST /corrections` saves the parent's fix and returns a corrected translation.
- **Validation:** text over 300 characters, or bad field values, now returns HTTP 422 instead of being silently accepted.
- **Keep the "?":** with the model on, the backend works out questions from the words. In fallback mode, a yes/no question is only recognised from a trailing "?", so never strip it from typed text.

## Tasks

### 1. Update `frontend/src/api.js`
Replace the `translate` export and add `correct`. `JSON.stringify` drops `undefined` values, so optional fields that aren't set are simply not sent.

```js
// Shapes are in CONTRACT.md. Both options are optional.
export const translate = (text, { emotion, faceEmotions } = {}) =>
  post("/translate", { text, emotion, face_emotions: faceEmotions });

export const correct = (text, { meaning, emotion } = {}) =>
  post("/corrections", { text, meaning, emotion });
```

Make `post` surface the backend's reason on a 422, so the parent sees "Text is too long" and not a generic failure:

```js
async function post(path, body) {
  const res = await fetch(BASE + path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const { detail } = await res.json().catch(() => ({}));
    throw new Error(typeof detail === "string" ? detail : `${path} failed with ${res.status}`);
  }
  return res.json();
}
```

Existing calls such as `translate(sentence)` keep working.

**Done when:** `translate("time for bed")` resolves with `meaning`, `source` and `unsure` present.

### 2. Loading state on the Speak page (`frontend/src/pages/Translator.jsx`)
A normal translation makes two model calls, and a hard sentence can make up to six. Expect 2 to 10 seconds, and in the worst case up to about 45 seconds before the backend gives up and returns its best attempt.

- Show "Translating…" and disable the Sign it and Speak buttons while waiting.
- Keep the previous signs on screen until the new result arrives.
- On an error, show the message from `api.js` and re-enable the buttons.

**Done when:** you can't send a second sentence while one is in flight, and an error never leaves the buttons disabled.

### 3. Show the meaning and the trust level
Under the signer, show one line: "I understood: {meaning}". Next to it, show a badge from `source` and `unsure`:

| Response | Badge text |
|---|---|
| `source: "phrase-bank"` | Checked by a fluent signer |
| `source: "model"`, `unsure: false` | No badge, or "AI translation" |
| `source: "model"`, `unsure: true` | Not sure about this one. Check with a signer. |
| `source: "fallback"` | Offline: rough word-by-word version |

Do the same for each page of the Storybook (`frontend/src/pages/Storybook.jsx`). Every sentence carries the same fields.

**Done when:** a fallback translation (run the backend with no API key) shows the offline badge.

### 4. One-tap correction
Next to "I understood: …", add a Fix button. It opens:
- a text box prefilled with the current `meaning`;
- six emotion buttons (neutral, happy, sad, angry, surprised, worried), with the current `emotion` selected.

On save, call `correct(originalText, { meaning, emotion })`, sending only the fields the parent changed, and replace the result with the response. `originalText` must be exactly the text sent to `/translate`.

Parents correct meaning and emotion only. There is no UI for correcting individual signs; that goes to a fluent signer.

**Done when:** correcting the emotion to "surprised" re-signs the sentence with `emotion: "surprised"`, and translating the same sentence again keeps it.

### 5. Send face emotion scores when the camera is on
Person 1 is writing `frontend/src/lib/faceEmotion.js` (see [`3d-signer.md`](3d-signer.md)). It gives you the parent's averaged face scores for the time they were speaking, or `null`.

In the Speak page:
1. Start face sampling when listening starts (`listen()` in `speech.js`).
2. Stop it when the transcript arrives.
3. Pass the result as `faceEmotions`: `translate(text, { faceEmotions: scores ?? undefined })`.

When the camera is off, denied or sees no face, send nothing. The backend works without it. Never send video frames.

**Done when:** with the camera on, the request body includes `face_emotions`; with it off, the field is absent.

### 6. Family settings and the speaker picker
- A small settings screen that loads `GET /family` and saves with `PUT /family`: child's name, age in months, and the family members (name plus which avatar). Show 422 reasons.
- On the Speak page, a "Who's talking?" picker with one button per member. Send the chosen member's `id` as `speaker` in `/translate`, and pass that member's `avatar` to `SignPlayer` as the `avatar` prop so the child sees that parent's signer.
- Voice detection of who is talking is a stretch goal. Tap-to-pick is the demo.

**Done when:** switching the picker changes the avatar and the `speaker` field in the request.

### 6b. Send voice loudness
While the parent holds the talk button, measure the mic level with the Web Audio API (an `AnalyserNode` on a `getUserMedia({audio: true})` stream, RMS in dB every 100 ms, ignoring silence). Compare the sentence's average with that parent's normal level (their first sentence, with a "reset my normal voice" button) and send `loudness = (dB - normal dB) / 12`, clamped to -1..1. Mics and rooms differ, so never send an absolute volume, and never send audio. `backend/dev.html` has a working version you can copy.

**Pitch too:** on the same audio frames, run [pitchy](https://github.com/ianprime0509/pitchy) (MIT, `import { PitchDetector } from "pitchy"`). Keep frames with clarity above 0.9 and 70 to 500 Hz, take the sentence's median, compare it with the parent's normal pitch (set with the loudness baseline) and send `pitch = semitones above normal / 6`, clamped to -1..1. `backend/dev.html` does this too.

**Done when:** speaking louder or higher than usual sends a positive `loudness` or `pitch`, and the request leaves out whichever one the mic couldn't measure.

### 7. Highlight new signs and the progress screen
- Every `/translate` and `/corrections` response has `new_signs`. Highlight those signs in the sign list ("New sign!"), because they widen the child's vocabulary.
- A Progress page that calls `GET /progress` (add `?speaker=<id>` for one parent):
  - "You used N different signs this week (M last week)" from `variety`.
  - "Signs to try next" from `catch_up.in_app`: each one tappable to see it signed.
  - Keep the tone encouraging. Never show a grade or say the child is behind.

**Done when:** a sign used for the first time is highlighted, and the Progress page shows the weekly count and the suggestions.

## Who owns what
| File | Owner | Your role |
|---|---|---|
| `frontend/src/api.js`, `pages/*`, `styles.css` | You | Edit |
| `frontend/src/components/SignPlayer.jsx` | Person 1 | Pass `signs`, `face`, `emotion`, `avatar`; don't edit |
| `frontend/src/lib/faceEmotion.js` | Person 1 | Import and call; don't edit |
| `frontend/src/lib/speech.js` | Person 3 | Import; don't edit |

## Testing without an API key
Start the backend without `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` set. Every translation then comes back as `source: "fallback"`, `unsure: true`, almost instantly. That's enough to build and test all five tasks before the key is set up.

## Checklist
- [ ] `api.js` sends `emotion` and `face_emotions`, has `correct()`, and shows 422 reasons.
- [ ] Speak page shows a loading state and can't double-send.
- [ ] Meaning line and trust badge on the Speak page and every Storybook page.
- [ ] Fix button calls `/corrections` and replaces the result.
- [ ] Face scores are sent only when the camera is on and a face was seen.
- [ ] Settings screen saves the family profile; the speaker picker sends `speaker` and switches the avatar.
- [ ] `new_signs` are highlighted, and the Progress page shows `variety` and `catch_up.in_app`.
