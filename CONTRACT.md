# Contract between the three parts

Agree on this once. Nobody changes a shape here without telling the other two.

## shared/vocab.json
The list of signs the whole app knows. One entry per sign:

```json
{"gloss": "MILK", "english": ["milk"]}
```

- `gloss` is the sign's label, in capitals. It is the ID used everywhere.
- `english` lists the spoken words that map to it.
- A sign only counts as supported when all three parts handle it: the recogniser can detect it, the translator can produce it, and the player can show it.

## POST /translate  (parent speaks, app signs)
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

## POST /recognize  (child signs, app reads)
Request: `{"frames": [[[x, y, z], ... 21 points], ... one entry per video frame]}`
Each frame is the 21 hand landmarks from MediaPipe for one hand.

Response: `{"sign": "MILK", "confidence": 0.91}`
`sign` is `null` when nothing is recognised.

## GET /vocab
Returns `shared/vocab.json` as is.

## Ports
- Backend: `http://localhost:8000`
- Frontend: `http://localhost:5173`
