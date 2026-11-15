// Text helpers for the Reader: split a document into sentences /translate accepts, and find which
// words of a sentence belong to the sign being shown.

// Sentences of at most `max` characters (the /translate limit); long ones are cut at word boundaries.
export function splitSentences(text, max = 300) {
  const pieces = text
    .replace(/\r/g, "")
    .split(/\n+/)
    .flatMap((line) => line.match(/[^.!?]+(?:[.!?]+["'”’)\]]*|$)/g) || [])
    .map((s) => s.replace(/\s+/g, " ").trim())
    .filter((s) => /[\p{L}\p{N}]/u.test(s));
  const out = [];
  for (const s of pieces) {
    if (s.length <= max) { out.push(s); continue; }
    let chunk = "";
    for (const word of s.split(" ")) {
      if (chunk && (chunk + " " + word).length > max) { out.push(chunk); chunk = ""; }
      chunk = chunk ? `${chunk} ${word}` : word.slice(0, max);
    }
    if (chunk) out.push(chunk);
  }
  return out;
}

const norm = (w) => w.toLowerCase().replace(/[^a-z0-9']/g, "").replace(/'s$/, "");

// Splits a sentence into word and in-between tokens (spaces, punctuation), so words can be highlighted in place.
export function tokenize(sentence) {
  return sentence.split(/([A-Za-z0-9'’]+)/).filter(Boolean).map((t) => ({ text: t, word: /^[A-Za-z0-9'’]+$/.test(t) ? norm(t.replace(/’/g, "'")) : "" }));
}

// The English words that a gloss stands for: its own name (ALL-DONE -> all, done) plus the vocab's words.
export function wordsForGlosses(glosses, vocab) {
  const words = new Set();
  for (const g of glosses) {
    for (const part of g.split(/[-_ ]/)) if (part) words.add(norm(part));
    const entry = vocab.find((v) => v.gloss === g);
    for (const w of entry?.english || []) words.add(norm(w));
  }
  words.delete("");
  return words;
}
