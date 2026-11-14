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

Request: `{"text": "do you want more milk?", "emotion": "happy"}`

`emotion` is optional. It is the speaker's tone: one of `neutral`, `happy`, `sad`, `angry`, `surprised`, `worried`. Send it when the frontend knows it. When it is left out, the backend works it out from the words.

Response:
```json
{
  "signs": [{"gloss": "MILK", "known": true}, {"gloss": "MORE", "known": true}],
  "face": "yes-no-question",
  "emotion": "happy",
  "checked": false
}
```
- `signs` is in signing order, not English word order.
- `known: false` means there is no sign for that word, so the player fingerspells it.
- `face` is the grammar: one of `statement`, `yes-no-question`, `wh-question`. It sets the eyebrows.
- `emotion` is the feeling. It sets the rest of the face and how big or sharp the signing is.
- `face` and `emotion` are separate on purpose. In ASL the eyebrows mark a question whatever the mood, so an angry question needs both.
- `checked: true` means the translation came from the human-checked phrase bank, not from the model.

## shared/phrases.json  (the phrase bank)
Translations a fluent signer has checked. The translator uses these before anything else.

```json
[{"english": "Do you want more milk?", "signs": ["MILK", "MORE", "YOU", "WANT"], "face": "yes-no-question"}]
```
Matching ignores capitals and punctuation. The file starts empty: only add an entry once a fluent signer has confirmed it.

## GET /books  and  GET /books/{id}  (storybook pivot)
`GET /books` returns `[{"id": "pips-morning", "title": "Pip's Morning"}]`.

`GET /books/{id}` returns the book with every sentence already translated:
```json
{
  "id": "pips-morning",
  "title": "Pip's Morning",
  "sentences": [{"text": "More milk?", "signs": [{"gloss": "MORE", "known": true}], "face": "yes-no-question", "emotion": "neutral", "checked": false}]
}
```
Each sentence has the same fields as a `/translate` response. An unknown id returns 404.

A book is a `.txt` file in `shared/books/`: the first line is the title, then one sentence per line.

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
