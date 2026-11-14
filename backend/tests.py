"""Offline tests with a fake model. Run from the repo root: python -m backend.tests"""
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest import mock

from datetime import datetime, timedelta, timezone

from backend import books, corrections, family, llm, progress as P
from backend import translate as T
from backend.llm import LLMUnavailable

GOOD = {"signs": ["YOU", "WANT", "MORE", "MILK"], "face": "yes-no-question", "emotion": "neutral", "meaning": "Does the child want more milk?"}
OK = {"english": "x", "same_meaning": True, "problem": ""}
BAD = {"english": "y", "same_meaning": False, "problem": "lost the question"}


class FakeModel:
    """Scripted replies in order; an Exception instance is raised. Counts calls."""

    def __init__(self, translations=(), checks=()):
        self.t, self.c, self.t_calls, self.c_calls = list(translations), list(checks), [], []

    def _next(self, queue):
        r = queue.pop(0)
        if isinstance(r, Exception):
            raise r
        return r

    def translate(self, **kw):
        self.t_calls.append(kw)
        return self._next(self.t)

    def back_translate(self, **kw):
        self.c_calls.append(kw)
        return self._next(self.c)

    @property
    def calls(self):
        return len(self.t_calls) + len(self.c_calls)


def raises(fn, *a, **kw):
    try:
        fn(*a, **kw)
    except ValueError as e:
        return str(e)
    raise AssertionError("expected ValueError")


def glosses(r):
    return [s["gloss"] for s in r["signs"]]


def test_validation_errors():
    assert "non-empty" in raises(T.translate, "   ")
    assert "non-empty" in raises(T.translate, 5)
    assert "300" in raises(T.translate, "a" * 301)
    assert "emotion" in raises(T.translate, "hi", "not-a-real-emotion")
    assert "unknown face" in raises(T.translate, "hi", None, {"joyful": 0.5})
    assert "0 to 1" in raises(T.translate, "hi", None, {"happy": 1.5})
    assert "0 to 1" in raises(T.translate, "hi", None, {"happy": True})
    assert "meaning_hint" in raises(T.translate, "hi", None, None, "m" * 301)


def test_face_mapping():
    assert T.face_emotion({"fearful": 0.7}) == ("worried", 0.7)
    top, score = T.face_emotion({"disgusted": 0.3, "angry": 0.4, "happy": 0.5})
    assert top == "angry" and abs(score - 0.7) < 1e-9
    assert T.face_emotion({"neutral": 0.9, "happy": 0.1}) is None  # neutral never overrides
    assert T.face_emotion(None) is None


def test_face_threshold_on_fallback():
    off = dict(offline=True, phrases={})
    assert T.translate("Hello", face_emotions={"sad": 0.6}, **off)["emotion"] == "sad"
    assert T.translate("Hello", face_emotions={"sad": 0.59}, **off)["emotion"] == "neutral"
    assert T.translate("I love you", face_emotions={"neutral": 0.9}, **off)["emotion"] == "happy"
    assert T.translate("Hello", "happy", {"sad": 0.9}, **off)["emotion"] == "happy"


def test_phrase_bank_no_model_and_precedence():
    bank = {T._key("Do you want more milk?"): {"english": "Do you want more milk?", "signs": ["MILK", "MORE", "YOU", "WANT"], "emotion": "worried", "meaning": "Offering milk"}}
    m = FakeModel()
    r = T.translate("do you want MORE milk", phrases=bank, model=m)
    assert m.calls == 0 and r["source"] == "phrase-bank" and r["unsure"] is False
    assert glosses(r) == ["MILK", "MORE", "YOU", "WANT"] and r["emotion"] == "worried" and r["meaning"] == "Offering milk"
    assert r["face"] == "statement"  # no entry face, no question mark
    assert T.translate("Do you want more milk?", face_emotions={"happy": 0.8}, phrases=bank, model=m)["emotion"] == "happy"
    assert T.translate("Do you want more milk?", "sad", {"happy": 0.8}, phrases=bank, model=m)["emotion"] == "sad"
    bare = {T._key("Hello"): {"english": "Hello", "signs": ["YES"]}}
    r = T.translate("Hello", phrases=bare, model=m)
    assert r["meaning"] == "Hello" and r["emotion"] == "neutral" and r["face"] == "statement"


def test_bank_with_meaning_hint_goes_to_model_unsure():
    bank = {T._key("Do you want more milk?"): {"english": "Do you want more milk?", "signs": ["MILK"]}}
    m = FakeModel([GOOD], [OK])
    r = T.translate("Do you want more milk?", meaning_hint="offering a refill", phrases=bank, model=m)
    assert r["source"] == "model" and r["unsure"] is True
    assert m.t_calls[0]["meaning_hint"] == "offering a refill" and len(m.t_calls[0]["examples"]) == 1


def test_model_happy_path_and_fs():
    out = dict(GOOD, signs=["YOU", "FS:Pip's", "LOVE", "FS:AB-1"], emotion="happy")
    m = FakeModel([out], [OK])
    r = T.translate("You love Pip's AB-1", phrases={}, model=m)
    assert r["source"] == "model" and r["unsure"] is False and r["emotion"] == "happy"
    assert r["signs"][1] == {"gloss": "PIP'S", "known": False} and r["signs"][0] == {"gloss": "YOU", "known": True}
    assert set(r) == {"signs", "face", "emotion", "meaning", "source", "unsure"}
    assert m.t_calls[0]["timeout"] <= 45 and m.c_calls[0]["text"] == "You love Pip's AB-1"


def test_model_output_validation():
    assert T.validate_model_output(GOOD) == []
    for bad in ({"signs": []}, dict(GOOD, signs=["PIZZA"]), dict(GOOD, signs=["FS:a b"]), dict(GOOD, signs="YOU"),
                dict(GOOD, face="x"), dict(GOOD, emotion="x"), dict(GOOD, meaning=""), dict(GOOD, meaning="m" * 301), []):
        assert T.validate_model_output(bad), bad


def test_invalid_output_retried_once_then_fallback():
    m = FakeModel([dict(GOOD, signs=["PIZZA"]), dict(GOOD, face="nope")])
    r = T.translate("Hello", phrases={}, model=m)
    assert len(m.t_calls) == 2 and m.c_calls == [] and m.t_calls[1]["previous"]["problem"]
    assert r["source"] == "fallback" and r["unsure"] is True
    m = FakeModel([dict(GOOD, signs=["PIZZA"]), GOOD], [OK])  # retry succeeds
    assert T.translate("Hello", phrases={}, model=m)["source"] == "model"


def test_selfcheck_mismatch_then_pass():
    better = dict(GOOD, signs=["MORE", "MILK", "YOU", "WANT"])
    m = FakeModel([GOOD, better], [BAD, OK])
    r = T.translate("Do you want more milk?", phrases={}, model=m)
    assert r["unsure"] is False and glosses(r) == better["signs"]
    assert m.t_calls[1]["previous"] == {"signs": GOOD["signs"], "problem": "lost the question"}


def test_selfcheck_mismatch_twice_keeps_latest_unsure():
    better = dict(GOOD, signs=["MORE", "MILK"])
    m = FakeModel([GOOD, better], [BAD, {"oops": 1}])  # malformed check also fails
    r = T.translate("Do you want more milk?", phrases={}, model=m)
    assert r["source"] == "model" and r["unsure"] is True and glosses(r) == ["MORE", "MILK"]


def test_llm_unavailable_falls_back():
    m = FakeModel([LLMUnavailable("down")])
    r = T.translate("Do you want more milk?", phrases={}, model=m)
    assert r["source"] == "fallback" and r["unsure"] is True and r["meaning"] == "Do you want more milk?"
    assert glosses(r) == ["YOU", "WANT", "MORE", "MILK"] and r["face"] == "yes-no-question"
    assert T.translate("I love pizza", phrases={}, model=FakeModel([LLMUnavailable("x")]))["signs"][-1] == {"gloss": "PIZZA", "known": False}


def test_llm_unavailable_during_selfcheck_keeps_candidate():
    m = FakeModel([dict(GOOD, emotion="happy")], [LLMUnavailable("down")])
    r = T.translate("Do you want more milk?", "sad", phrases={}, model=m)
    assert r["source"] == "model" and r["unsure"] is True and glosses(r) == GOOD["signs"] and r["emotion"] == "sad"
    better = dict(GOOD, signs=["MORE", "MILK"])
    m = FakeModel([GOOD, better], [BAD, LLMUnavailable("down")])  # down on the second check: keep the re-translation
    r = T.translate("Do you want more milk?", phrases={}, model=m)
    assert r["source"] == "model" and r["unsure"] is True and glosses(r) == ["MORE", "MILK"]
    m = FakeModel([GOOD, LLMUnavailable("down")], [BAD])  # down during the re-translate: keep the first candidate
    r = T.translate("Do you want more milk?", phrases={}, model=m)
    assert r["source"] == "model" and r["unsure"] is True and glosses(r) == GOOD["signs"]


def test_explicit_emotion_forced():
    m = FakeModel([dict(GOOD, emotion="happy")], [OK])
    r = T.translate("Do you want more milk?", "angry", {"happy": 0.9}, phrases={}, model=m)
    assert r["emotion"] == "angry" and m.t_calls[0]["emotion"] == "angry"
    assert T.translate("x", phrases={}, model=FakeModel([GOOD], [OK]), face_emotions={"sad": 0.9})["emotion"] == "neutral"  # model decides


def test_correction_overrides():
    fixes = [{"text": "Hello!", "meaning": "old", "emotion": "sad"}, {"text": "hello", "meaning": "greeting", "emotion": "happy"},
             {"text": "other", "emotion": "angry"}]
    m = FakeModel([dict(GOOD, emotion="neutral")], [OK])
    r = T.translate("Hello", phrases={}, model=m, corrections=fixes)
    assert r["emotion"] == "happy" and m.t_calls[0]["meaning_hint"] == "greeting" and len(m.t_calls[0]["corrections"]) == 3
    m = FakeModel([GOOD], [OK])
    r = T.translate("Hello", "sad", phrases={}, model=m, corrections=fixes, meaning_hint="mine")
    assert r["emotion"] == "sad" and m.t_calls[0]["meaning_hint"] == "mine"
    bank = {"hello": {"english": "Hello", "signs": ["YES"]}}
    r = T.translate("Hello", phrases=bank, model=m, corrections=[{"text": "Hello", "emotion": "worried"}])
    assert r["source"] == "phrase-bank" and r["emotion"] == "worried"


def test_time_budget():
    m = FakeModel([GOOD], [OK])
    r = T.translate("Hello", phrases={}, model=m, budget_seconds=0)
    assert m.calls == 0 and r["source"] == "fallback"
    ticks = iter([0, 0] + [100] * 10)  # time runs out after the first model call
    m = FakeModel([GOOD], [OK])
    with mock.patch.object(T.time, "monotonic", lambda: next(ticks)):
        r = T.translate("Do you want more milk?", phrases={}, model=m)
    assert len(m.t_calls) == 1 and m.c_calls == [] and r["source"] == "model" and r["unsure"] is True


def test_existing_translate_checks():
    r = T.translate("Do you want more milk?", phrases={}, offline=True)
    assert glosses(r) == ["YOU", "WANT", "MORE", "MILK"] and r["face"] == "yes-no-question" and r["emotion"] == "neutral"
    assert T.translate("What do you want?", offline=True)["face"] == "wh-question"
    assert T.translate("Time for bed", offline=True)["signs"] == [{"gloss": "SLEEP", "known": True}]
    assert T.translate("I love you", offline=True, phrases={})["emotion"] == "happy"
    assert T.translate("I love you", emotion="sad", offline=True)["emotion"] == "sad"
    assert all("signs" in p for p in T.load_phrases().values())
    assert "checked" not in r


def test_corrections_storage():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "sub" / "c.json"
        assert corrections.load_corrections(p) == []
        e = corrections.save_correction("Hi there", "greeting", None, path=p)
        corrections.save_correction("Bye", None, "sad", path=p)
        got = corrections.load_corrections(p)
        assert [c["text"] for c in got] == ["Hi there", "Bye"] and got[0] == e and got[1]["emotion"] == "sad" and got[0]["saved_at"]
        assert not list(p.parent.glob("*.tmp"))
        for args in (("", "m"), ("a" * 301, "m"), ("x", "m" * 301), ("x", ""), ("x", None, "bogus"), ("x",), (5, "m"),
                     (" " + "a" * 300, "m"), ("x", "m" * 300 + " ")):  # same length rule as /translate, so nothing is saved then rejected
            raises(corrections.save_correction, *args, path=p)
        p.write_text("{not json")
        assert corrections.load_corrections(p) == []
        p.write_text('[{"text": "ok"}, 5, {"text": 7}, null]')
        assert corrections.load_corrections(p) == [{"text": "ok"}]
        p.write_text('{"a": 1}')
        assert corrections.load_corrections(p) == []


def _book_dir(d, text="Test Book\nPip wants milk.\nI love you.\n"):
    (Path(d) / "tb.txt").write_text(text)
    return Path(d)


def test_books_build_and_get():
    with tempfile.TemporaryDirectory() as d:
        bd = _book_dir(d)
        m = FakeModel([GOOD, dict(GOOD, signs=["ME", "LOVE", "YOU"])], [OK, OK])
        built = books.build_book("tb", book_dir=bd, model=m, phrases={})
        cache = json.loads((bd / "tb.signs.json").read_text())
        assert cache == built and len(cache["sentences"]) == 2 and cache["source_hash"] and cache["title"] == "Test Book"
        before = m.calls
        got = books.get_book("tb", book_dir=bd, phrases={})
        assert m.calls == before and glosses(got["sentences"][1]) == ["ME", "LOVE", "YOU"] and got["sentences"][0]["source"] == "model"
        bank = {"i love you": {"english": "I love you", "signs": ["LOVE", "YOU"], "meaning": "bank"}}
        got = books.get_book("tb", book_dir=bd, phrases=bank)  # bank re-applied at read time
        assert got["sentences"][1]["source"] == "phrase-bank" and glosses(got["sentences"][1]) == ["LOVE", "YOU"]
        assert got["sentences"][0]["source"] == "model"
        (bd / "tb.txt").write_text("Test Book\nPip wants milk.\nI love you!\nMore.\n")  # stale cache
        got = books.get_book("tb", book_dir=bd, phrases={})
        assert [s["source"] for s in got["sentences"]] == ["fallback"] * 3 and all(s["unsure"] for s in got["sentences"])
        files = sorted(p.name for p in bd.iterdir())
        assert files == ["tb.signs.json", "tb.txt"]


def test_books_build_writes_even_with_fallback():
    with tempfile.TemporaryDirectory() as d:
        bd = _book_dir(d)
        built = books.build_book("tb", book_dir=bd, model=FakeModel([LLMUnavailable("x")] * 2), phrases={})
        assert (bd / "tb.signs.json").exists() and all(s["source"] == "fallback" and s["unsure"] for s in built["sentences"])


def test_books_unknown_and_traversal():
    assert books.get_book("nope") is None
    assert books.get_book("../translate") is None
    assert books.get_book("../../etc/passwd") is None
    assert books.list_books()[0] == {"id": "pips-morning", "title": "Pip's Morning"}
    b = books.get_book("pips-morning")
    assert b["sentences"][3]["face"] == "yes-no-question" and "checked" not in b["sentences"][3]


def test_llm_extract_json():
    assert llm.extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert llm.extract_json('Sure! Here it is: {"a": {"b": [1, 2]}} hope that helps {') == {"a": {"b": [1, 2]}}
    for bad in ("no json", "{broken", "[1, 2]"):
        try:
            llm.extract_json(bad)
        except LLMUnavailable:
            continue
        raise AssertionError(bad)


def test_llm_no_key_unavailable():
    # _load_env is patched out so a developer's real .env can never turn this into a real API call
    with mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(llm, "_load_env", lambda: None):
        for provider in (None, "openai"):
            if provider:
                os.environ["LLM_PROVIDER"] = provider
            try:
                llm.call_json("s", "u", 1)
            except LLMUnavailable as e:
                assert "KEY" in str(e)
            else:
                raise AssertionError("expected LLMUnavailable")
        os.environ.update(LLM_PROVIDER="openai", OPENAI_API_KEY="sk-secret")
        try:
            llm.call_json("s", "u", 1)
        except LLMUnavailable as e:
            assert "LLM_MODEL" in str(e) and "sk-secret" not in str(e)
        os.environ.update(LLM_PROVIDER="anthropic", ANTHROPIC_API_KEY="sk-secret")
        try:
            llm.call_json("s", "u", 1)  # SDK not installed here, or the request fails: either way unavailable
        except LLMUnavailable as e:
            assert "sk-secret" not in str(e)


def test_prompts():
    s, u = llm.translate_prompt("Hi", T.VOCAB, {"happy": 0.5}, "sad", "greeting", [{"english": "a", "signs": ["YES"]}], [{"text": "t"}], {"signs": ["NO"], "problem": "bad"})
    assert "MILK: milk" in s + u and "FS:WORD" in s and "fluent signer" in s and "outrank" in u and "greeting" in u and "bad" in u and "Sentence: Hi" in u


def test_review_fixes():
    # corrections merge: the latest meaning survives a later emotion-only correction; bad stored values are ignored
    m = FakeModel([GOOD], [OK])
    fixes = [{"text": "Do you want more milk?", "meaning": "offering milk", "emotion": None},
             {"text": "do you want more milk", "meaning": None, "emotion": "happy"},
             {"text": "do you want more milk", "meaning": None, "emotion": "furious"}]
    r = T.translate("Do you want more milk?", model=m, phrases={}, corrections=fixes)
    assert r["emotion"] == "happy" and m.t_calls[0]["meaning_hint"] == "offering milk"
    # a blank meaning is treated as missing, so an emotion-only correction from the frontend is accepted
    with tempfile.TemporaryDirectory() as d:
        e = corrections.save_correction("hi", meaning="  ", emotion="sad", path=Path(d) / "c.json")
        assert e["meaning"] is None and e["emotion"] == "sad"
        assert "meaning, an emotion" in raises(corrections.save_correction, "hi", meaning="", path=Path(d) / "c.json")
    # a book line over 300 characters does not break the book
    with tempfile.TemporaryDirectory() as d:
        Path(d, "long.txt").write_text("Long\n" + "word " * 70 + "\nI love you.\n", encoding="utf-8")
        b = books.get_book("long", book_dir=d, phrases={})
        assert b["sentences"][0]["source"] == "fallback" and b["sentences"][0]["unsure"] is True
        assert glosses(b["sentences"][1]) == ["ME", "LOVE", "YOU"]


def test_evaluate():
    from backend import evaluate as E
    sentences = json.loads(E.SENTENCES.read_text(encoding="utf-8"))
    vocab = {v["gloss"] for v in T.VOCAB}
    for s in sentences:  # every expected sign must exist, or the score can never be met
        assert set(s.get("expect", {}).get("signs", [])) <= vocab, s
        T.validate(s["text"], None, s.get("face_emotions"), None)
    rows, summary = E.evaluate(sentences, offline=True, phrases={})
    assert summary["sentences"] == len(sentences) and summary["source"] == {"fallback": len(sentences)}
    # scoring with a fake model: right face, wrong emotion, one key sign missing
    m = FakeModel([{"signs": ["MILK", "FS:PIZZA"], "face": "yes-no-question", "emotion": "happy", "meaning": "m"}], [OK])
    rows, summary = E.evaluate([{"text": "do you want more milk", "expect": {"face": "yes-no-question", "emotion": "neutral", "signs": ["MILK", "MORE"]}}],
                               model=m, phrases={})
    r = rows[0]
    assert r["face_ok"] is True and r["emotion_ok"] is False and r["missing_signs"] == "MORE"
    assert r["signs"] == "MILK PIZZA*" and r["fingerspelled"] == 1 and r["fully_signed"] is False
    assert summary["key signs present"] == "1/2" and summary["question type correct"] == "1/1"
    with tempfile.TemporaryDirectory() as d:
        path = E.write_review_sheet(rows, Path(d))
        assert "signer_review" in path.read_text(encoding="utf-8").splitlines()[0]


def test_asl_lex():
    from backend import asl_lex as A
    with tempfile.TemporaryDirectory() as d:
        src = Path(d, "signdata.csv")
        cols = ["EntryID", "LemmaID", "SignFrequency(M)", "Iconicity(M)", "InCDI", "CDISemanticCategory", "bglm_aoa",
                "DominantTranslation", "NondominantTranslations", "Handshape.2.0", "MajorLocation.2.0", "MinorLocation.2.0"]
        rows = [["eat_1", "eat", "6.84", "6.1", "Yes", "Action Signs", "20", "", "", "flat_o", "Head", "Mouth"],
                ["eat_2", "eat", "6.68", "5.9", "No", "", "", "", "", "o", "Head", "Mouth"],
                ["ball", "ball", "4.63", "", "Yes", "Toys", "19", "", "", "curved_5", "Neutral", "Neutral"],
                ["hungry", "hungry", "5.77", "3.13", "Yes", "Descriptive Signs", "29", "hungry", "hunger, wish", "c", "Body", "TorsoTop"]]
        src.write_text("\n".join(",".join(f'"{c}"' for c in r) for r in [cols, *rows]) + "\n", encoding="utf-8")
        entries = A.import_csv(src)
        assert entries[0]["english"] == ["eat"] and entries[0]["child_vocab"] is True and entries[2]["iconicity"] is None
        assert entries[3]["english"] == ["hungry", "hunger", "wish"] and entries[0]["location"] == "Head / Mouth"
        todo = A.write_files(entries, [{"gloss": "EAT", "asl_lex": "eat_1"}], Path(d, "lex.json"), Path(d, "next.md"))
        assert todo == 2  # ball and hungry; eat_1 is already in vocab, eat_2 isn't child vocabulary
        md = Path(d, "next.md").read_text(encoding="utf-8")
        assert md.index("| ball |") < md.index("| hungry |") and "CC BY-NC" in md  # earliest-learned first, credited
        index = A.load(Path(d, "lex.json"))
        assert A.has_sign("EAT", index) == "eat_1" and A.has_sign("hunger", index) == "hungry" and A.has_sign("pizza", index) is None
    # every sign in vocab.json is linked to a real ASL-LEX entry
    if A.LEX.exists():
        entries = {e["entry"] for e in json.loads(A.LEX.read_text(encoding="utf-8"))["signs"]}
        assert all(v["asl_lex"] in entries for v in T.VOCAB), [v["gloss"] for v in T.VOCAB if v["asl_lex"] not in entries]


def test_family_profile():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d, "family.json")
        assert family.load_family(p) == {"child_name": None, "child_age_months": None, "members": []}
        p.write_text("{oops")
        assert family.load_family(p)["members"] == []  # corrupt file -> default
        saved = family.save_family({"child_name": " Mia ", "child_age_months": 20,
                                    "members": [{"id": "mom", "name": " Mom ", "avatar": None}]}, p)
        assert saved["child_name"] == "Mia" and saved["members"][0]["name"] == "Mom" and family.load_family(p) == saved
        assert family.save_family({"child_name": "  "}, p)["child_name"] is None
        m = {"id": "a", "name": "A", "avatar": None}
        bad = [{"child_name": "x" * 61}, {"child_age_months": True}, {"child_age_months": 217}, {"child_age_months": 1.5},
               {"members": [dict(m, id=str(i)) for i in range(9)]}, {"members": [dict(m, id="Bad Id")]},
               {"members": [m, m]}, {"members": [dict(m, name=" ")]}, {"members": [dict(m, name="x" * 41)]},
               {"members": [dict(m, avatar="x" * 41)]}, {"members": [dict(m, avatar=3)]}]
        for b in bad:
            try:
                family.save_family(b, p)
            except ValueError:
                continue
            raise AssertionError(f"accepted {b}")
        assert family.save_family({"child_age_months": 0}, p)["child_age_months"] == 0
        assert family.save_family({"members": [dict(m, avatar=" ")]}, p)["members"][0]["avatar"] is None


def test_usage_and_new_signs():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d, "usage.json")
        assert P.new_signs(["MILK", "MILK", "EAT"], p) == ["MILK", "EAT"]
        P.log_usage([], path=p)
        assert not p.exists()  # empty logs nothing
        P.log_usage(["MILK"], "mom", path=p)
        assert P.new_signs(["EAT", "MILK", "EAT", "HELP"], p) == ["EAT", "HELP"]


LEX = {"milk": {"entry": "milk", "english": ["milk"], "frequency": 6, "iconicity": 2, "child_vocab": True, "age_learned_months": 18},
       "eat": {"entry": "eat_1", "english": ["eat"], "frequency": 7, "iconicity": 5, "child_vocab": True, "age_learned_months": 12},
       "ball": {"entry": "ball", "english": ["ball"], "frequency": 5, "iconicity": None, "child_vocab": True, "age_learned_months": 12},
       "cat": {"entry": "cat", "english": ["cat"], "frequency": 5, "iconicity": 4, "child_vocab": True, "age_learned_months": 12},
       "dog": {"entry": "dog", "english": ["dog"], "frequency": 5, "iconicity": 1, "child_vocab": True, "age_learned_months": 30},
       "the": {"entry": "the", "english": ["the"], "frequency": 5, "iconicity": 1, "child_vocab": False, "age_learned_months": 10},
       "noage": {"entry": "noage", "english": ["noage"], "frequency": 5, "iconicity": 1, "child_vocab": True, "age_learned_months": None}}
VOC = [{"gloss": "MILK", "english": ["milk"], "asl_lex": "milk"}, {"gloss": "EAT", "english": ["eat"], "asl_lex": "eat_1"},
       {"gloss": "CAT", "english": ["cat"], "asl_lex": "cat"}]


def test_progress():
    now = datetime(2026, 1, 20, tzinfo=timezone.utc)
    with tempfile.TemporaryDirectory() as d:
        p = Path(d, "usage.json")
        P.log_usage(["MILK", "EAT"], "mom", now - timedelta(days=10), p)
        P.log_usage(["EAT"], "dad", now - timedelta(days=2), p)
        P.log_usage(["MILK", "HELP"], "mom", now - timedelta(days=1), p)
        r = P.progress(None, None, now, p, LEX, VOC)
        assert r["signs_used"] == ["MILK", "EAT", "HELP"] and r["variety"] == {"this_week": 3, "last_week": 2}
        assert P.progress(None, "dad", now, p, LEX, VOC)["signs_used"] == ["EAT"]
        # no age: every child_vocab entry with an age, minus what the family used (milk, eat_1); cat in_app, ball not yet
        r = P.progress(None, None, now, p, LEX, VOC)["catch_up"]
        assert [x["entry"] for x in r["in_app"]] == ["cat"] and r["in_app"][0]["gloss"] == "CAT"
        assert [x["entry"] for x in r["not_yet_animated"]] == ["ball", "dog"]
        # dad has not used milk; age 18 drops dog; age 12 entries sort by frequency then iconicity (None last)
        r = P.progress(18, "dad", now, p, LEX, VOC)["catch_up"]
        assert [x["entry"] for x in r["in_app"]] == ["cat", "milk"] and [x["entry"] for x in r["not_yet_animated"]] == ["ball"]
        assert set(r["in_app"][0]) == {"gloss", "entry", "english", "age_learned_months"}
        # real ASL-LEX file: "water" is shadowed in the word index (swing lists it) but must still be suggested
        r = P.progress(30, None, now, Path(d, "none.json"), vocab=[{"gloss": "WATER", "english": ["water"], "asl_lex": "water"}])
        assert [x["gloss"] for x in r["catch_up"]["in_app"]] == ["WATER"], r["catch_up"]["in_app"]
        # hand-edited log: a naive time and a non-text sign must not crash
        Path(d, "bad.json").write_text('[{"t": "2026-01-19T00:00:00", "signs": ["MILK", {"x": 1}]}]')
        assert P.new_signs(["MILK", "EAT"], Path(d, "bad.json")) == ["EAT"]
        assert P.progress(None, None, now, Path(d, "bad.json"), LEX, VOC)["variety"]["this_week"] == 0


def test_routes():
    try:
        from fastapi.testclient import TestClient
    except ImportError:
        print("skip test_routes: httpx not installed")
        return
    from backend import main
    with tempfile.TemporaryDirectory() as d, mock.patch.object(family, "PATH", Path(d, "f.json")), \
            mock.patch.object(P, "USAGE_PATH", Path(d, "u.json")), \
            mock.patch.object(main, "save_family", lambda b: family.save_family(b, Path(d, "f.json"))), \
            mock.patch.object(main, "load_family", lambda: family.load_family(Path(d, "f.json"))), \
            mock.patch.object(main, "log_usage", lambda g, s=None: P.log_usage(g, s, path=Path(d, "u.json"))), \
            mock.patch.object(main, "new_signs", lambda g: P.new_signs(g, Path(d, "u.json"))):
        c = TestClient(main.app)
        assert c.put("/family", json={"child_age_months": 999}).status_code == 422
        assert c.put("/family", json={"child_name": "Mia", "child_age_months": 20}).status_code == 200
        assert c.get("/family").json()["child_name"] == "Mia"
        with mock.patch.object(main, "translate", lambda *a, **k: {"signs": [{"gloss": "MILK", "known": True}, {"gloss": "X", "known": False}]}):
            assert c.post("/translate", json={"text": "milk", "speaker": "Bad Id"}).status_code == 422
            assert c.post("/translate", json={"text": "milk", "speaker": "mom"}).json()["new_signs"] == ["MILK"]
            assert c.post("/translate", json={"text": "milk"}).json()["new_signs"] == []


def run():
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    failed = 0
    for n, f in tests:
        try:
            f()
        except Exception as e:
            failed += 1
            print(f"FAIL {n}: {type(e).__name__}: {e}")
    print(f"{len(tests) - failed}/{len(tests)} tests passed")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    run()
