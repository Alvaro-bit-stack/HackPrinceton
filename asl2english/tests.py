"""Offline tests for ASL -> English, with a fake model (no key, no network). Run from the repo root:
    python -m asl2english.tests
"""
import sys
import tempfile
from pathlib import Path
from unittest import mock

import numpy as np

from asl2english import asl_to_english as A
from asl2english import prompts, recognize as RZ
from backend.llm import LLMUnavailable

ML = Path(__file__).parent.parent / "ml"
GOOD = {"english": "Maya wants more milk.", "alternatives": [], "emotion": "neutral", "is_question": False,
        "confidence": 0.9, "unsure": False}


class FakeModel:
    """Scripted replies in order; an Exception instance is raised. Records what it was asked."""

    def __init__(self, replies=()):
        self.replies, self.calls = list(replies), []

    def understand(self, **kw):
        self.calls.append(kw)
        r = self.replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def sign(gloss, confidence=0.9, alternatives=()):
    return {"gloss": gloss, "confidence": confidence, "alternatives": list(alternatives)}


def raises(fn, *a, **kw):
    try:
        fn(*a, **kw)
    except ValueError as e:
        return str(e)
    raise AssertionError("expected ValueError")


def reference_clips():
    z = np.load(ML / "model_selfcheck.npz", allow_pickle=False)
    return {str(l): [f.tolist() for f in z["frames"][i][: int(z["lengths"][i])]] for i, l in enumerate(z["labels"])}


# ---------------------------------------------------------------- gloss -> English

def test_clean_two_sign_sentence():
    m = FakeModel([GOOD])
    r = A.understand([sign("MILK"), sign("MORE")], child_name="Maya", model=m)
    assert r["english"] == "Maya wants more milk." and r["source"] == "model"
    assert r["unsure"] is False and r["low_confidence_signs"] == [] and r["is_question"] is False
    assert r["confidence"] == round(0.9 * 0.9, 2) and len(m.calls) == 1
    assert [s["gloss"] for s in m.calls[0]["signs"]] == ["MILK", "MORE"]  # signing order reaches the model
    assert set(r) >= {"english", "alternatives", "emotion", "is_question", "confidence", "unsure", "low_confidence_signs"}


def test_question_face_makes_a_question():
    # the model ignored the raised brows: rejected, told why, and the retry is a question
    m = FakeModel([GOOD, dict(GOOD, english="Does Maya want more milk?", is_question=True)])
    r = A.understand([sign("MILK"), sign("MORE")], face="yes-no-question", child_name="Maya", model=m)
    assert r["is_question"] is True and r["english"].endswith("?") and len(m.calls) == 2
    assert "question" in m.calls[1]["previous"]["problem"]
    assert m.calls[0]["face"] == "yes-no-question"
    # with no model at all, the fallback still turns the face into a question
    r = A.understand([sign("MILK"), sign("MORE")], face="yes-no-question", model=FakeModel([LLMUnavailable("x")]))
    assert r["english"] == "milk more?" and r["is_question"] is True
    # and a statement face stays a statement
    r = A.understand([sign("MILK"), sign("MORE")], face="statement", model=FakeModel([LLMUnavailable("x")]))
    assert r["english"] == "milk more" and r["is_question"] is False


def test_wh_sign_at_end_is_question_in_fallback():
    r = A.understand([sign("YOU"), sign("EAT"), sign("WHAT")], model=FakeModel([LLMUnavailable("x")]))
    assert r["is_question"] is True and r["english"] == "you eat what?"


def test_low_confidence_sign_flagged():
    m = FakeModel([dict(GOOD, english="Maya maybe wants water.", unsure=False)])
    r = A.understand([sign("WANT"), sign("WATER", 0.4, [{"gloss": "MILK", "confidence": 0.3}])], child_name="Maya", model=m)
    assert r["low_confidence_signs"] == ["WATER"] and r["unsure"] is True  # code forces it even if the model says sure
    shown = m.calls[0]["signs"]
    assert shown[1]["low"] is True and shown[0]["low"] is False
    assert "LOW CONFIDENCE" in prompts.understand_prompt(**{k: v for k, v in m.calls[0].items() if k != "timeout"})[1]
    fb = A.understand([sign("WANT"), sign("WATER", 0.4)], model=FakeModel([LLMUnavailable("x")]))
    assert fb["english"] == "want maybe water" and fb["low_confidence_signs"] == ["WATER"]


def test_invalid_output_retried_once_then_fallback():
    m = FakeModel([{"english": ""}, {"oops": 1}])
    r = A.understand([sign("ALL-DONE"), sign("EAT")], model=m)
    assert len(m.calls) == 2 and m.calls[1]["previous"]["problem"]  # the retry was told what was wrong
    assert r == {"english": "all done eat", "alternatives": [], "emotion": "neutral", "is_question": False,
                 "confidence": round(0.3 * 0.9, 2), "unsure": True, "low_confidence_signs": [],
                 "look_alike_signs": [], "source": "fallback"}
    m = FakeModel([{"english": ""}, GOOD])  # retry succeeds
    assert A.understand([sign("MILK"), sign("MORE")], child_name="Maya", model=m)["source"] == "model"


def test_invented_words_rejected():
    m = FakeModel([dict(GOOD, english="Maya wants more milk, please."), GOOD])
    r = A.understand([sign("MILK"), sign("MORE")], child_name="Maya", model=m)
    assert "please" in m.calls[1]["previous"]["problem"] and r["english"] == "Maya wants more milk."
    # "wants" reads the intent of a request; "now" adds meaning the child did not sign; inflections and hedges are fine
    assert A.invented_words("Maya wants water now.", {"WATER"}, "Maya") == ["now"]
    assert A.invented_words("Maya is drinking water and ate.", {"WATER", "DRINK", "EAT"}, "Maya") == []
    assert A.invented_words("Maybe your child is signing milk?", {"MILK"}) == []
    assert A.invented_words("Maya doesn't want to sleep.", {"WANT", "SLEEP"}, "Maya") == ["not"]
    assert A.invented_words("Maya doesn't want to sleep.", {"WANT", "SLEEP"}, "Maya", negation_ok=True) == []


def test_alternatives_make_unsure():
    m = FakeModel([dict(GOOD, english="Dad, play!", alternatives=["Dad is playing."], unsure=False)])
    r = A.understand([sign("DAD"), sign("PLAY")], model=m)
    assert r["alternatives"] == ["Dad is playing."] and r["unsure"] is True
    m = FakeModel([dict(GOOD, alternatives=["a", "b", "c"]), dict(GOOD, english="Dad, play!")])
    A.understand([sign("DAD"), sign("PLAY")], model=m)
    assert "alternatives" in m.calls[1]["previous"]["problem"]


def test_emotion_rules():
    m = FakeModel([dict(GOOD, emotion="happy")])  # an explicit emotion is used as is
    assert A.understand([sign("MILK"), sign("MORE")], emotion="sad", child_name="Maya", model=m)["emotion"] == "sad"
    m = FakeModel([dict(GOOD, emotion="neutral")])  # a strong face beats a neutral reading, but never changes the signs
    r = A.understand([sign("MILK"), sign("MORE")], face_emotions={"happy": 0.8}, child_name="Maya", model=m)
    assert r["emotion"] == "happy" and r["english"] == "Maya wants more milk."
    assert A.understand([sign("NO")], face_emotions={"fearful": 0.9}, model=FakeModel([LLMUnavailable("x")]))["emotion"] == "worried"


def test_llm_unavailable_and_time_budget():
    r = A.understand([sign("HELP")], model=FakeModel([LLMUnavailable("ANTHROPIC_API_KEY is not set")]))
    assert r["source"] == "fallback" and r["english"] == "help"
    m = FakeModel([GOOD])
    assert A.understand([sign("HELP")], model=m, budget_seconds=0.5)["source"] == "fallback" and not m.calls


def test_bad_input_raises():
    for bad, word in [([], "signs"), ([sign("PIZZA")], "gloss"), ([sign("MILK", 1.5)], "confidence"),
                      ([sign("MILK", True)], "confidence"), ([sign("MILK")] * 13, "signs"), ("MILK", "signs"),
                      ([sign("MILK", 0.9, [{"gloss": "DOG", "confidence": 0.1}])], "gloss")]:
        assert word in raises(A.understand, bad, model=FakeModel()), bad
    ok = [sign("MILK")]
    assert "face" in raises(A.understand, ok, face="frown", model=FakeModel())
    assert "head_shake" in raises(A.understand, ok, head_shake="yes", model=FakeModel())
    assert "emotion" in raises(A.understand, ok, emotion="bored", model=FakeModel())
    assert "face emotion" in raises(A.understand, ok, face_emotions={"bored": 0.5}, model=FakeModel())
    assert "face emotion" in raises(A.understand, ok, face_emotions={"happy": 2}, model=FakeModel())
    assert "child_name" in raises(A.understand, ok, child_name="x" * 61, model=FakeModel())


def test_prompt_contents():
    system, user = prompts.understand_prompt(
        signs=[dict(sign("MILK"), low=False), dict(sign("MORE", 0.5, [{"gloss": "EAT", "confidence": 0.2}]), low=True)],
        meanings={"MILK": ["milk"], "MORE": ["more"], "EAT": ["eat"]}, child_name="Maya", face="wh-question",
        head_shake=True, previous={"reply": {"english": "x"}, "problem": "bad"})
    assert "young child" in system and "Never invent meaning" in system and "alternatives" in system
    assert "1. MILK" in user and "2. MORE" in user and "could also be EAT" in user and "LOW CONFIDENCE" in user
    assert "Maya" in user and "wh-question" in user and "head shake" in user and "rejected: bad" in user


# ---------------------------------------------------------------- ASL-LEX: meanings and look-alikes

def test_asl_lex_meanings():
    from asl2english import lexicon as L
    assert "father" in L.MEANINGS["DAD"] and "finish" in L.MEANINGS["ALL-DONE"] and "nap" in L.MEANINGS["SLEEP"]
    assert L.MEANINGS["YOU"] == ["you"]  # ASL-LEX has none: vocab.json's words stay
    # translations widen what the English may say, phrase by phrase
    assert A.invented_words("Maya's father helps.", {"DAD", "HELP"}, "Maya") == []
    assert A.invented_words("Maya finished her nap.", {"ALL-DONE", "SLEEP"}, "Maya") == []
    m = FakeModel([dict(GOOD, english="Daddy!")])
    assert A.understand([sign("DAD")], model=m)["source"] == "model"
    assert "father" in m.calls[0]["meanings"]["DAD"]
    with tempfile.TemporaryDirectory() as d:  # missing lexicon: vocab meanings only, no look-alikes, no crash
        meanings, pairs = L.load(Path(d, "none.json"))
    assert meanings["DAD"] == ["dad", "daddy", "father"] and pairs == {}


def test_look_alike_flagged():
    want = sign("WANT", 0.7, [{"gloss": "WHAT", "confidence": 0.25}])
    assert A.look_alikes_of(want) == ["WHAT"]
    assert A.look_alikes_of(sign("WANT", 0.9, [{"gloss": "WHAT", "confidence": 0.05}])) == []  # too faint
    assert A.look_alikes_of(sign("WANT", 0.7, [{"gloss": "WATER", "confidence": 0.25}])) == []  # not alike
    # the model must offer the other reading; it forgot, was told, and fixed it
    first = dict(GOOD, english="Maya wants it.")
    second = dict(first, alternatives=["What?"])
    m = FakeModel([first, second])
    r = A.understand([sign("ME"), want], child_name="Maya", model=m)
    assert "LOOKS LIKE" in m.calls[1]["previous"]["problem"] and r["alternatives"] == ["What?"]
    assert r["look_alike_signs"] == [{"gloss": "WANT", "could_be": ["WHAT"]}] and r["unsure"] is True
    assert "LOOKS LIKE WHAT" in prompts.understand_prompt(**{k: v for k, v in m.calls[0].items() if k != "timeout"})[1]
    fb = A.understand([sign("ME"), want], model=FakeModel([LLMUnavailable("x")]))
    assert fb["english"] == "me want (or what)" and fb["look_alike_signs"][0]["could_be"] == ["WHAT"]


def test_build_lexicon_from_dataset_files():
    from asl2english import build_lexicon as B
    assert B.clean_translations("eat_1", "food", "consume, food, eat, MILKasym, interrogative,  ") == ["food", "consume", "eat"]
    with tempfile.TemporaryDirectory() as d:
        ds = Path(d)
        (ds / "Phonology").mkdir()
        (ds / "signdata.csv").write_text(
            "EntryID,Code,DominantTranslation,NondominantTranslations,SignBankEnglishTranslations\n"
            "want,C_1,,,\"want, wants\"\nwhat_1,D_2,,,\"what, WHAT\"\nmilk,A_3,,,\"dairy, milk\"\n", encoding="utf-8")
        (ds / "Phonology" / "NeigborPairs.csv").write_text(
            "target,neighbor,num_matched_features,matched_features,num_missed_features,missed_features\n"
            'C_1,D_2,14,"a, b",2,"c"\nD_2,C_1,13,"a",3,"c"\nA_3,C_1,5,"a",11,"c"\nC_1,X_9,15,"a",1,"c"\n', encoding="utf-8")
        vocab = ds / "vocab.json"
        vocab.write_text('[{"gloss": "WANT", "english": ["want"], "asl_lex": "want"}, {"gloss": "WHAT", "english": ["what"], '
                         '"asl_lex": "what_1"}, {"gloss": "MILK", "english": ["milk"], "asl_lex": "milk"}, '
                         '{"gloss": "NEW", "english": ["new"], "asl_lex": "missing"}]', encoding="utf-8")
        data = B.build(ds, vocab)
        B.write(data, ds / "lexicon.json")
        assert (ds / "lexicon.json").exists()
    assert data["signs"]["MILK"]["translations"] == ["dairy", "milk"] and data["signs"]["WHAT"]["translations"] == ["what"]
    assert data["signs"]["NEW"] == {"asl_lex": None, "translations": []}
    assert data["look_alikes"] == [["WANT", "WHAT", 14]]  # best count per pair; weak pairs and non-vocab signs dropped
    assert "ASL-LEX" in data["credit"]


# ---------------------------------------------------------------- recognition and segmentation

def test_segmentation_on_reference_clips():
    clips = reference_clips()
    for g, c in clips.items():  # each recorded clip on its own is one sign, ranked list restricted to the vocab
        r = RZ.recognize_signs(c)
        assert r["recognizer"] == RZ.MODEL and [s["glosses"][0]["gloss"] for s in r["signs"]] == [g], (g, r)
        gl = r["signs"][0]["glosses"]
        assert 1 <= len(gl) <= RZ.TOP_K and all(0 <= x["confidence"] <= 1 for x in gl)
        assert [x["confidence"] for x in gl] == sorted((x["confidence"] for x in gl), reverse=True)
    # two signs with the hands dropped in between come back as two signs, in order
    r = RZ.recognize_signs(clips["MILK"] + [None] * 6 + clips["MORE"])
    assert [s["glosses"][0]["gloss"] for s in r["signs"]] == ["MILK", "MORE"]
    assert r["signs"][0]["end"] <= r["signs"][1]["start"]
    # the same sign twice stays twice when the hands drop in between
    r = RZ.recognize_signs(clips["MORE"] + [[]] * 6 + clips["MORE"])
    assert [s["glosses"][0]["gloss"] for s in r["signs"]] == ["MORE", "MORE"]


def test_recognizer_edge_cases_and_stand_in():
    assert RZ.recognize_signs([None] * 10)["signs"] == []
    hand = np.random.default_rng(0).random((21, 3)).tolist()
    assert RZ.recognize_signs([hand] * 2)["signs"] == []  # too short to be a sign
    with mock.patch.object(RZ.R, "load_templates", lambda: {}):
        r = RZ.recognize_signs(reference_clips()["MILK"], model=None)
    assert r["recognizer"] == RZ.STAND_IN and r["signs"] == []
    t = {"MILK": [RZ.R.normalize(hand).tolist()]}
    with mock.patch.object(RZ.R, "load_templates", lambda: t):
        r = RZ.recognize_signs([hand] * 8, model=None)
    assert r["recognizer"] == RZ.STAND_IN and r["signs"][0]["glosses"][0]["gloss"] == "MILK"


def test_validate_frames():
    hand = np.zeros((21, 3)).tolist()
    RZ.validate_frames([hand, None, [], hand])
    for bad, word in [([], "non-empty"), ([hand] * (RZ.MAX_FRAMES + 1), "at most"), ([hand[:5]], "21 points"),
                      ([[[float("nan")] * 3] * 21], "finite"), ([[["a", "b", "c"]] * 21], "21 points"), ("x", "non-empty")]:
        assert word in raises(RZ.validate_frames, bad), bad


# ---------------------------------------------------------------- route

def test_route():
    try:
        from fastapi.testclient import TestClient
    except ImportError:
        print("skip test_route: httpx not installed")
        return
    from asl2english import asl2eng
    clips = reference_clips()
    c = TestClient(asl2eng.app)
    reply = dict(GOOD, english="Mia wants more milk?", is_question=True)
    with mock.patch.object(A, "DEFAULT_MODEL", FakeModel([reply])), \
            mock.patch.object(asl2eng, "load_family", lambda: {"child_name": "Mia"}):
        r = c.post("/understand", json={"frames": clips["MILK"] + [None] * 6 + clips["MORE"], "face": "yes-no-question"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["english"] == "Mia wants more milk?" and body["is_question"] is True
        assert [s["glosses"][0]["gloss"] for s in body["signs"]] == ["MILK", "MORE"] and body["recognizer"] == "model"
        assert A.DEFAULT_MODEL.calls[0]["child_name"] == "Mia"
    with mock.patch.object(A, "DEFAULT_MODEL", FakeModel([LLMUnavailable("no key")])), \
            mock.patch.object(asl2eng, "load_family", lambda: {"child_name": None}):
        body = c.post("/understand", json={"frames": clips["WATER"]}).json()
        assert body["source"] == "fallback" and body["english"] == "water" and body["unsure"] is True
    nothing = c.post("/understand", json={"frames": [None] * 10}).json()
    assert nothing["english"] == "" and nothing["source"] == "none"
    hand = clips["MILK"][0]
    for bad in [{"frames": []}, {"frames": [hand[:5]]}, {"frames": [hand] * (RZ.MAX_FRAMES + 1)},
                {"frames": [hand], "emotion": "bored"}, {"frames": [hand], "face_emotions": {"happy": 3}},
                {"frames": [hand], "face": "frown"}, {"frames": "x"}]:
        assert c.post("/understand", json=bad).status_code == 422, bad
    # the existing routes still work on the combined app
    assert c.post("/recognize", json={"frames": clips["MILK"]}).json()["sign"] == "MILK"
    assert c.get("/health").json() == {"ok": True}


def test_frames_never_logged():
    import logging
    records = []
    handler = logging.Handler()
    handler.emit = records.append
    logging.getLogger().addHandler(handler)
    try:
        A.understand([sign("MILK")], model=FakeModel([{"oops": 1}, LLMUnavailable("down")]))
    finally:
        logging.getLogger().removeHandler(handler)
    assert records and not any("0." in r.getMessage() for r in records)  # failure names only, no numbers from the input


def test_evaluate():
    from asl2english import evaluate as E
    items = [{"signs": ["MILK", "MORE"], "intended": ["Maya wants more milk."], "is_question": False},
             {"signs": ["MORE"], "face": "yes-no-question", "intended": ["More?"], "is_question": True}]
    replies = [dict(GOOD, english="Maya wants more milk!"), dict(GOOD, english="More?", is_question=True, unsure=True)]
    rows, summary = E.evaluate(items, model=FakeModel(replies))
    assert summary["exact intent"] == "2/2" and summary["question type correct"] == "2/2" and summary["unsure"] == "1/2"
    with tempfile.TemporaryDirectory() as d:
        path = E.write_review_sheet(rows, Path(d))
        text = path.read_text(encoding="utf-8")
    assert "signer_review" in text and "Maya wants more milk!" in text
    data = E.load_items(E.ITEMS)
    assert len(data) >= 20 and all(set(x["signs"]) <= A.GLOSSES for x in data)
    _, offline = E.evaluate(data, offline=True)
    assert offline["source"] == {"fallback": len(data)}


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
