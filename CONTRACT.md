# Contract between the three parts

Agree on this once. Nobody changes a shape here without telling the other two.

## shared/vocab.json
The list of signs the whole app knows. One entry per sign:

```json
{"gloss": "MILK", "english": ["milk"], "asl_lex": "milk"}
```

- `gloss` is the sign's label, in capitals. It is the ID used everywhere.
- `english` lists the spoken words that map to it.
- `asl_lex` is the matching entry in ASL-LEX (`shared/asl_lex.json`), the sign dictionary we use for sign data. Every sign must have one.
- A sign only counts as supported when the translator can produce it and the signer can show it.

## POST /translate  (the core: text in, signs out)
Used by both the Speak page and the Storybook page.

Request:
```json
{"text": "you ate all of it", "emotion": "happy", "face_emotions": {"happy": 0.8, "surprised": 0.1}, "speaker": "mom", "loudness": 0.4, "pitch": 0.3}
```
| Field | Required | Rules |
|---|---|---|
| `text` | yes | 1 to 300 characters. |
| `emotion` | no | One of `neutral`, `happy`, `sad`, `angry`, `surprised`, `worried`. Only send it when you know it for sure, for example after the parent picked it. It always wins. |
| `face_emotions` | no | The parent's face while speaking, from the face model (MediaPipe blendshapes turned into seven scores, see `backend/dev.html`), averaged over the sentence. Keys must be among `neutral`, `happy`, `sad`, `angry`, `fearful`, `disgusted`, `surprised`; values 0 to 1. Leave it out when the camera is off or no face was seen. |
| `speaker` | no | The family member talking: a member `id` from `/family`, such as `mom` (lowercase letters, digits and `-`, up to 30 characters). Used to keep a per-parent progress count. |
| `loudness` | no | How loud the parent spoke compared with their own normal voice: -1 (much quieter) to 1 (much louder), 0 normal. The frontend measures it from the mic level; never send audio. It sets how strong the feeling is, not which feeling. |
| `pitch` | no | The parent's voice pitch compared with their own normal: -1 (much lower) to 1 (much higher), 0 normal. The frontend measures it from the mic with a pitch detector (about 6 semitones higher = 1). Like `loudness`, it mainly sets intensity; raised pitch also hints at a more agitated or excited feeling. |
| `face_frames` | no | **Opt-in only.** 1 to 3 small JPEG snapshots of the parent's face (base64, no `data:` prefix, at most 200,000 characters each; 256 px wide is plenty) from the strongest moments of the sentence. The AI looks at them to judge the emotion, which catches sad and worried far better than the scores. They go to the AI provider with this one request and are never stored or logged. Only send them when the parent has turned the option on. |
| `face_neutral` | no | **Opt-in only.** One snapshot of the parent's relaxed face, taken when they record their neutral face, so the AI can compare. Ignored without `face_frames`. |

Response:
```json
{
  "signs": [{"gloss": "YOU", "known": true}, {"gloss": "PIZZA", "known": false}],
  "face": "statement",
  "emotion": "happy",
  "meaning": "Praising the child for finishing their food",
  "source": "model",
  "unsure": false,
  "new_signs": ["YOU"],
  "intensity": 0.6,
  "tone_reason": "praise for finishing the food; happy face agrees; voice a bit raised"
}
```
- `signs` is in signing order, not English word order.
- `known: false` means there is no sign for that word, so the player fingerspells it.
- `face` is the grammar: one of `statement`, `yes-no-question`, `wh-question`. It sets the eyebrows.
- `emotion` is the feeling, one of the six above. It sets the rest of the face.
- `intensity` (0 to 1) is how strong the feeling is: 0.2 calm, 0.5 clear, 0.8 or more very strong. It sets how big and sharp the signing and the face are. A firm warning is `angry` at low intensity; real anger is `angry` at high intensity.
- `tone_reason` is one short line on which signals decided the emotion and intensity. Show it in testing tools; parents don't need it.
- How the three tone signals combine: the words decide which emotion when they carry intent (a warning, praise, "be careful"); the face decides when the words are ambiguous ("you ate all of it"); a face that disagrees with clear words, such as smiling while warning, doesn't change the emotion but can soften the intensity; loudness and pitch raise or lower the intensity. A neutral answer never overrides a strong face (one emotion scoring 0.6 or more in `face_emotions`): the face's emotion is used instead. An explicit `emotion` always wins.
- `face` and `emotion` are separate on purpose. In ASL the eyebrows mark a question whatever the mood, so an angry question needs both.
- `meaning` is one line on what the backend understood the parent to mean. Show it so the parent can correct it.
- `source` says where the translation came from:
  - `phrase-bank`: checked by a fluent signer.
  - `model`: written by the language model. `unsure` says whether it passed its self-check.
  - `fallback`: the model couldn't be reached, so this is a rough word-for-word version.
- `unsure: true` means don't trust it: the self-check failed, the model timed out, `source` is `fallback`, or the parent corrected the meaning of a phrase-bank sentence. Show this to the parent.
- `new_signs` lists the signs in this sentence the family has never used before. Highlight them: they widen the child's vocabulary. Every successful `/translate` is logged for `/progress`.
- A request can take several seconds, because the backend translates and then double-checks. Show a loading state.

Errors: invalid input returns HTTP 422. The `detail` field explains why. It is a string for checks the backend makes, such as length, and a list for checks FastAPI makes first, such as a wrong type or an `emotion` outside the six.

## POST /corrections  (the parent fixes what the app understood)
Request:
```json
{"text": "you ate all of it", "meaning": "I'm surprised, not proud", "emotion": "surprised"}
```
- `text` is the original sentence, exactly as sent to `/translate`.
- `meaning` (up to 300 characters) and `emotion` (one of the six) are optional, but send at least one.
- A blank or whitespace-only `meaning` is treated as missing. With no emotion either, that is a 422.

Response: a fresh translation in the same shape as `/translate` (including `new_signs`), with the correction applied. It isn't logged again for `/progress`. The correction is saved, so the same sentence uses it next time, and it is shown to the model as an example for other sentences.

Parents correct meaning and emotion only. Corrections to the signs themselves go to a fluent signer, who adds them to the phrase bank.

## shared/phrases.json  (the phrase bank)
Translations a fluent signer has checked. The translator uses these before anything else.

```json
[{"english": "Do you want more milk?", "signs": ["MILK", "MORE", "YOU", "WANT"], "face": "yes-no-question", "emotion": "neutral", "meaning": "Offering the child more milk"}]
```
- `english` and `signs` are required. `face`, `emotion` and `meaning` are optional.
- Matching ignores capitals and punctuation.
- The file starts empty: only add an entry once a fluent signer has confirmed it.

## GET /books  and  GET /books/{id}  (storybook pivot)
`GET /books` returns `[{"id": "pips-morning", "title": "Pip's Morning"}]`.

`GET /books/{id}` returns the book with every sentence already translated:
```json
{
  "id": "pips-morning",
  "title": "Pip's Morning",
  "sentences": [{"text": "More milk?", "signs": [{"gloss": "MORE", "known": true}, {"gloss": "MILK", "known": true}], "face": "yes-no-question", "emotion": "neutral", "intensity": 0.2, "tone_reason": "plain offer", "meaning": "Asking if the child wants more milk", "source": "model", "unsure": false}]
}
```
Each sentence has `text` plus the same fields as a `/translate` response. An unknown id returns 404.

- **Where the files live:** a book is a `.txt` file in `shared/books/`, with the title on the first line and then one sentence per line.
- **Translated ahead of time:** books are translated once with `python -m backend.books build <id>`, which saves `shared/books/<id>.signs.json`. Opening a book never calls the model, so pages load instantly.
- **Not yet translated:** if a book hasn't been built, or its text changed since, the page still opens. Sentences that match the phrase bank come back as `phrase-bank`; the rest come back as `fallback` and `unsure`.

## POST /recognize  (stretch: child signs, app reads)
Request: `{"frames": [[[x, y, z], ... 21 points], ... one entry per video frame]}`
Each frame is the 21 hand landmarks from MediaPipe for one hand.

Response: `{"sign": "MILK", "confidence": 0.91}`
`sign` is `null` when nothing is recognised.

## GET /family  and  PUT /family  (family profile)
```json
{"child_name": "Maya", "child_age_months": 30,
 "members": [{"id": "mom", "name": "Mom", "avatar": "pip-mom"}, {"id": "dad", "name": "Dad", "avatar": "pip-dad"}]}
```
- `PUT` replaces the whole profile and returns the saved version. `GET` returns it, or the empty default (`null`s and `[]`) before it's set.
- `child_name` up to 60 characters. `child_age_months` a whole number 0 to 216.
- Up to 8 `members`. `id` is 1 to 30 lowercase letters, digits and `-`, unique; `name` 1 to 40 characters; `avatar` is an avatar id the 3D signer knows (up to 40 characters, not checked), or `null`. Names are trimmed; a blank `child_name` or `avatar` is saved as `null`.
- Invalid input returns 422.
- The child's age never makes the translation simpler. It only decides which early signs show up in the catch-up list.

## GET /progress  (catch-up, not cap)
`GET /progress` for the whole family, or `GET /progress?speaker=mom` for one parent (then `signs_used`, `variety` and `catch_up` count only that parent's sentences). A `speaker` that isn't lowercase letters, digits and `-` (up to 30) returns 422.
```json
{
  "child_age_months": 30,
  "speaker": null,
  "signs_used": ["MILK", "MORE", "EAT"],
  "variety": {"this_week": 9, "last_week": 5},
  "catch_up": {
    "in_app": [{"gloss": "WATER", "entry": "water", "english": ["water"], "age_learned_months": 18}],
    "not_yet_animated": [{"entry": "ball", "english": ["ball"], "age_learned_months": 16}]
  }
}
```
- `signs_used`: the different signs used so far, in first-used order. `variety`: different signs used in the last 7 days and the 7 before. Show it as "more signs than last week", not a score.
- `catch_up`: signs children usually know by this age (ASL-LEX child vocabulary, learned at or before `child_age_months`) that this family hasn't used yet, earliest first. Up to 20 each. With no `child_age_months` set, every child-vocabulary sign counts. `age_learned_months` is a number and may come as `18.0`.
  - `in_app`: the app can already sign it. Suggest it to the parent.
  - `not_yet_animated`: no clip yet. Useful for the 3D signer's to-do list.
- The goal is to help the parent catch up to rich, everyday signing, never to cap what the child sees.

## GET /vocab
Returns `shared/vocab.json` as is.

## Ports
- Backend: `http://localhost:8000`
- Frontend: `http://localhost:5173`
