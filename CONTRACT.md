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

Request: `{"text": "do you want more milk?"}`

Response:
```json
{
  "signs": [{"gloss": "MILK", "known": true}, {"gloss": "MORE", "known": true}],
  "face": "yes-no-question"
}
```
- `signs` is in signing order, not English word order.
- `known: false` means there is no sign for that word, so the player fingerspells it.
- `face` is one of `statement`, `yes-no-question`, `wh-question`. The player uses it for the eyebrows, and the app shows the parent the matching cue.

## GET /books  and  GET /books/{id}  (storybook pivot)
`GET /books` returns `[{"id": "pips-morning", "title": "Pip's Morning"}]`.

`GET /books/{id}` returns the book with every sentence already translated:
```json
{
  "id": "pips-morning",
  "title": "Pip's Morning",
  "sentences": [{"text": "More milk?", "signs": [{"gloss": "MORE", "known": true}], "face": "yes-no-question"}]
}
```
Each sentence has the same `signs` and `face` fields as `/translate`. An unknown id returns 404.

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
