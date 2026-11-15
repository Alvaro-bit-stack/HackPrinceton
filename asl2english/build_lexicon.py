"""Extract what ASL -> English needs from the ASL-LEX 2.0 dataset in asl_dataset/ into asl2english/lexicon.json.

    python -m asl2english.build_lexicon

For each sign in shared/vocab.json (matched by its "asl_lex" entry id):
- translations: every English translation ASL-LEX lists (dominant, non-dominant and Sign Bank), cleaned.
- look_alikes: other vocab signs sharing many of ASL-LEX's 16 phonological features (handshape, location,
  movement...), from Phonology/NeigborPairs.csv. These are the pairs a camera is most likely to mix up.
The raw dataset is about 2.2 GB, so this runs once (about 20 s) and the app only reads the small JSON.
NeigborPairs.csv can be deleted afterwards; rebuilding then refreshes translations and keeps the saved pairs.
"""
import csv
import json
import os
import re
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent.parent
DATASET = ROOT / "asl_dataset"
VOCAB = ROOT / "shared" / "vocab.json"
OUT = Path(__file__).parent / "lexicon.json"
MIN_STORED_FEATURES = 9  # keep pairs from here up; the runtime threshold is asl_to_english.LOOK_ALIKE_FEATURES
NOT_MEANINGS = {"interrogative", "pronoun", "affirmative", "negative"}  # grammar labels in Sign Bank, not translations
CREDIT = ("ASL-LEX 2.0, Sehyr, Caselli, Cohen-Goldberg & Emmorey (2021), https://asl-lex.org, licensed CC BY-NC 4.0")


def clean_translations(*fields):
    """Comma-separated translation fields -> unique lowercase English, dropping ids (eat_1, MILKasym) and labels."""
    out = []
    for field in fields:
        for t in (field or "").split(","):
            t = t.strip()
            if not t or t != t.lower() or re.search(r"[_\d]", t) or t in NOT_MEANINGS:
                continue
            if t not in out:
                out.append(t)
    return out


def build(dataset=DATASET, vocab_path=VOCAB):
    vocab = json.loads(Path(vocab_path).read_text(encoding="utf-8"))
    with open(Path(dataset) / "signdata.csv", encoding="utf-8", errors="replace", newline="") as f:
        rows = {r["EntryID"]: r for r in csv.DictReader(f)}
    signs, code_to_gloss = {}, {}
    for v in vocab:
        r = rows.get(v.get("asl_lex"))
        if r is None:
            signs[v["gloss"]] = {"asl_lex": None, "translations": []}
            continue
        signs[v["gloss"]] = {"asl_lex": v["asl_lex"],
                             "translations": clean_translations(r["DominantTranslation"], r["NondominantTranslations"],
                                                                r["SignBankEnglishTranslations"])}
        code_to_gloss[r["Code"]] = v["gloss"]
    pairs_file = Path(dataset) / "Phonology" / "NeigborPairs.csv"
    if not pairs_file.exists():  # the 2.2 GB file is often deleted after the first build: keep the pairs we have
        old = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
        known = set(signs)
        pairs = [p for p in old.get("look_alikes", []) if p[0] in known and p[1] in known]
        print(f"{pairs_file} not found; keeping {len(pairs)} look-alike pairs from {OUT.name}")
        return {"credit": CREDIT, "features_total": 16, "signs": signs, "look_alikes": pairs}
    best = {}
    with open(pairs_file, encoding="utf-8", errors="replace") as f:
        next(f)
        for line in f:
            a = code_to_gloss.get(line[:line.find(",")])  # cheap filter: most of the 2.2 GB is about other signs
            if a is None:
                continue
            _, b_code, matched, _ = line.split(",", 3)
            b = code_to_gloss.get(b_code)
            if b and b != a and int(matched) >= MIN_STORED_FEATURES:
                key = tuple(sorted((a, b)))
                best[key] = max(best.get(key, 0), int(matched))
    pairs = [[a, b, n] for (a, b), n in sorted(best.items(), key=lambda kv: (-kv[1], kv[0]))]
    return {"credit": CREDIT, "features_total": 16, "signs": signs, "look_alikes": pairs}


def write(data, path=OUT):
    fd, tmp = tempfile.mkstemp(dir=Path(path).parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1)
        os.replace(tmp, path)  # readers never see a half-written file
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


if __name__ == "__main__":
    data = build()
    write(data)
    missing = [g for g, s in data["signs"].items() if s["asl_lex"] is None]
    print(f"{len(data['signs'])} signs, {len(data['look_alikes'])} look-alike pairs -> {OUT}")
    if missing:
        print("not found in ASL-LEX:", ", ".join(missing))
