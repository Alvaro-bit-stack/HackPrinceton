"""How the look-alike settings were chosen, and what they do, on the overnight WLASL landmark clips (ml/data).

    python -m asl2english.check_look_alikes            # validation split: used to choose the settings
    python -m asl2english.check_look_alikes --split test   # report once, after choosing; never tune on it

For every clip of a sign the model knows, it takes the model's ranked guesses and asks:
- confusion vs phonology: how much probability the model puts on each other sign, grouped by how many of
  ASL-LEX's 16 phonological features the two signs share;
- the flag: how often a correct answer is flagged (a false alarm the parent has to read past), and how often a
  wrong answer is flagged with the true sign offered as the other reading (a mistake caught).
"""
import argparse
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

from asl2english import asl_to_english as A
from asl2english.lexicon import LOOK_ALIKES
from asl2english.recognize import TOP_K

ML = Path(__file__).parent.parent / "ml"


def ranked_clips(split):
    sys.path.insert(0, str(ML))  # ml/dataset.py imports its neighbours as top-level modules
    import dataset as D
    import recognizer as R
    m = R.load_model()
    if m is None:
        raise SystemExit("ml/model.npz not found")
    classes = [str(c) for c in m["classes"]]
    known = [i for i, c in enumerate(classes) if c != R.OTHER]
    out = []
    for c in D.load_clips():
        if c.split != split or c.label not in classes or c.label == R.OTHER:
            continue
        x = R.sequence_features(c.seq, int(m["seq_len"]))
        if x is None:
            continue
        p = R.model_probs(m, x)
        out.append((c.label, sorted(((classes[i], float(p[i])) for i in known), key=lambda t: -t[1])))
    return out


def flag_stats(clips, features, minimum):
    old = A.LOOK_ALIKE_FEATURES, A.LOOK_ALIKE_MIN
    A.LOOK_ALIKE_FEATURES, A.LOOK_ALIKE_MIN = features, minimum
    try:
        right = wrong = false_alarm = caught = 0
        for label, ranked in clips:
            top = {"gloss": ranked[0][0], "confidence": ranked[0][1],
                   "alternatives": [{"gloss": g, "confidence": q} for g, q in ranked[1:TOP_K]]}
            could_be = A.look_alikes_of(top)
            if ranked[0][0] == label:
                right += 1
                false_alarm += bool(could_be)
            else:
                wrong += 1
                caught += label in could_be
        return right, wrong, false_alarm, caught
    finally:
        A.LOOK_ALIKE_FEATURES, A.LOOK_ALIKE_MIN = old


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--split", default="val")
    args = ap.parse_args()
    clips = ranked_clips(args.split)
    print(f"{args.split}: {len(clips)} clips of signs the model knows\n")

    mass = defaultdict(list)
    for label, ranked in clips:
        for g, q in ranked:
            if g != label:
                mass[LOOK_ALIKES.get(frozenset((label, g)), 0)].append(q)
    print("shared features | mean probability on the other sign | sign pairs x clips")
    for k in sorted(mass, reverse=True):
        print(f"{k:>15} | {np.mean(mass[k]):>34.3f} | {len(mass[k])}")
    print("(pairs under 9 shared features are not stored and show as 0)\n")

    print("features  min-conf  | correct flagged (false alarm) | wrong caught (true sign offered)")
    for features in (10, 11, 12, 14):
        for minimum in (0.05, 0.1, 0.2):
            right, wrong, fa, caught = flag_stats(clips, features, minimum)
            mark = "  <- in use" if (features, minimum) == (A.LOOK_ALIKE_FEATURES, A.LOOK_ALIKE_MIN) else ""
            print(f"{features:>8}  {minimum:>8}  | {fa:>3}/{right:<3} ({fa / max(right, 1):.0%}) {'':>13} | "
                  f"{caught}/{wrong}{mark}")


if __name__ == "__main__":
    main()
