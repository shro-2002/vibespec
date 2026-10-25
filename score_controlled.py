#!/usr/bin/env python3
"""Aggregate HUMAN ratings from private/eval2/ratings/*.csv (exported by rater.html). Un-blinds with blind_key.json.
Prints descriptive stats only. With few raters this is evidence to look at, not a significance claim."""
import csv, json, sys
from collections import defaultdict
from math import comb
from pathlib import Path

D = Path(__file__).parent / "private" / "eval2"
files = sorted((D / "ratings").glob("*.csv")) if (D / "ratings").exists() else []
if not files:
    sys.exit("No ratings yet: put raters' CSV files in private/eval2/ratings/. Nothing is fabricated.")
key = json.loads((D / "blind_key.json").read_text())
M = ("cultural_fit", "coherence", "usefulness", "feasibility")
scores, prefs, raters = defaultdict(list), defaultdict(int), set()
for f in files:
    for r in csv.DictReader(open(f)):
        raters.add(r["rater"])
        if r["plan"] == "overall":
            if r["overall_pref"]:
                prefs["tie" if r["overall_pref"] == "tie" else key[r["brief"]][r["overall_pref"]]] += 1
            continue
        arm = key[r["brief"]][r["plan"]]
        for m in M:
            if r[m]:
                scores[(arm, m)].append(float(r[m]))
print(f"raters: {len(raters)} ({', '.join(sorted(raters))})")
for m in M:
    a, b = scores[("A", m)], scores[("B", m)]
    if a and b:
        print(f"{m:13} A(Qloo) {sum(a)/len(a):.2f} (n={len(a)})  B(Qloo-free) {sum(b)/len(b):.2f} (n={len(b)})")
n = prefs["A"] + prefs["B"]
p = sum(comb(n, k) for k in range(max(prefs["A"], prefs["B"]), n + 1)) * 2 / 2**n if n else None
print(f"overall preference: A {prefs['A']}, B {prefs['B']}, tie {prefs['tie']}; two-sided sign test p = {p if p is None else round(min(p, 1), 3)} (ties excluded)")
