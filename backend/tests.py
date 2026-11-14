"""Offline tests with a fake model. Run from the repo root: python -m backend.tests"""
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest import mock

from backend import books, corrections, llm
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
