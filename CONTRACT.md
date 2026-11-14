# Contract between the three parts

Agree on this once. Nobody changes a shape here without telling the other two.

## shared/vocab.json
The list of signs the whole app knows. One entry per sign:

```json
{"gloss": "MILK", "english": ["milk"]}
```

- `gloss` is the sign's label, in capitals. It is the ID used everywhere.
- `english` lists the spoken words that map to it.
- A sign only counts as supported when the translator can produce it and the signer can show it.

## POST /translate  (the core: text in, signs out)
Used by both the Speak page and the Storybook page.

Request:
```json
{"text": "you ate all of it", "emotion": "happy", "face_emotions": {"happy": 0.8, "surprised": 0.1}}
```
| Field | Required | Rules |
|---|---|---|
| `text` | yes | 1 to 300 characters. |
| `emotion` | no | One of `neutral`, `happy`, `sad`, `angry`, `surprised`, `worried`. Only send it when you know it for sure, for example after the parent picked it. It always wins. |
| `face_emotions` | no | The parent's face while speaking, from face-api.js, averaged over the sentence. Keys must be among `neutral`, `happy`, `sad`, `angry`, `fearful`, `disgusted`, `surprised`; values 0 to 1. Leave it out when the camera is off or no face was seen. |

Response:
```json
{
  "signs": [{"gloss": "YOU", "known": true}, {"gloss": "PIZZA", "known": false}],
  "face": "statement",
  "emotion": "happy",
  "meaning": "Praising the child for finishing their food",
  "source": "model",
  "unsure": false
}
```
- `signs` is in signing order, not English word order.
- `known: false` means there is no sign for that word, so the player fingerspells it.
- `face` is the grammar: one of `statement`, `yes-no-question`, `wh-question`. It sets the eyebrows.
- `emotion` is the feeling, one of the six above. It sets the rest of the face and how big or sharp the signing is.
- `face` and `emotion` are separate on purpose. In ASL the eyebrows mark a question whatever the mood, so an angry question needs both.
- `meaning` is one line on what the backend understood the parent to mean. Show it so the parent can correct it.
- `source` says where the translation came from:
  - `phrase-bank`: checked by a fluent signer.
  - `model`: written by the language model. `unsure` says whether it passed its self-check.
  - `fallback`: the model couldn't be reached, so this is a rough word-for-word version.
- `unsure: true` means don't trust it: the self-check failed, the model timed out, `source` is `fallback`, or the parent corrected the meaning of a phrase-bank sentence. Show this to the parent.
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

Response: a fresh translation in the same shape as `/translate`, with the correction applied. The correction is saved, so the same sentence uses it next time, and it is shown to the model as an example for other sentences.

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
  "sentences": [{"text": "More milk?", "signs": [{"gloss": "MORE", "known": true}, {"gloss": "MILK", "known": true}], "face": "yes-no-question", "emotion": "neutral", "meaning": "Asking if the child wants more milk", "source": "model", "unsure": false}]
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

## GET /vocab
Returns `shared/vocab.json` as is.

## Ports
- Backend: `http://localhost:8000`
- Frontend: `http://localhost:5173`
