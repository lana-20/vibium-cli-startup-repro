#!/usr/bin/env python3
"""
Check the numbers in the report against the raw result files in `results/`.

    python3 verify.py

This does not re-run anything. It recomputes every headline figure from the
stored per-rep data and fails if the summary in a result file disagrees with its
own raw measurements -- so a hand-edited summary cannot pass.

Run `measure.py` if you want your own numbers; run this if you want to check ours.
"""
import json
import statistics as st
import sys
from pathlib import Path

RESULTS = Path(__file__).resolve().parent / "results"
fails = []


def check(label, cond, detail=""):
    print(f"  {'ok  ' if cond else 'FAIL'}  {label}" + (f"   [{detail}]" if detail else ""))
    if not cond:
        fails.append(label)


files = sorted(RESULTS.glob("n*.json"))
if not files:
    sys.exit("no result files in results/")

print(f"{len(files)} result files\n")
rows = []
for f in files:
    blob = json.loads(f.read_text())
    s, reps = blob["summary"], blob["per_rep"]
    good = [r for r in reps if r.get("shim_ok") and r.get("patched_ok")]

    # recompute from raw, do not trust the stored summary
    shim = st.median([r["shim_ms"] for r in good])
    pat = st.median([r["patched_ms"] for r in good])
    saving = shim - pat
    ratio = shim / pat
    floor = st.median([abs(r["shim_again_ms"] - r["shim_ms"]) for r in good])
    mism = sum(1 for r in reps for k in ("shim_ok", "patched_ok") if not r.get(k))

    print(f"{f.name}")
    check("n_scored matches the raw reps", s["n_scored"] == len(good), f"{len(good)}")
    check("saving recomputes", abs(s["saving_median_ms"] - saving) < 0.15, f"{saving:.1f}ms")
    check("ratio recomputes", abs(s["ratio_median"] - ratio) < 0.02, f"{ratio:.2f}x")
    check("noise floor recomputes", abs(s["noise_floor_median_ms"] - floor) < 0.15, f"{floor:.1f}ms")
    check("mismatch count matches", s["correctness_mismatches"] == mism, f"{mism}")
    check("zero correctness mismatches", mism == 0)
    check("saving clears the noise floor by 10x", saving > 10 * floor,
          f"{saving/floor:.0f}x floor")
    print()
    rows.append((f.stem, len(good), round(saving, 1), round(ratio, 2), round(floor, 1)))

print(f"{'run':<14}{'n':>5}{'saving':>9}{'ratio':>8}{'floor':>7}")
for name, n, sav, rat, fl in sorted(rows, key=lambda r: (r[1], r[0])):
    print(f"{name:<14}{n:>5}{sav:>9}{rat:>8}{fl:>7}")

sav = [r[2] for r in rows]
rat = [r[3] for r in rows]
print(f"\nacross {len(rows)} runs, {sum(r[1] for r in rows)} scored reps:")
print(f"  saving {min(sav)}-{max(sav)} ms   ({100*(max(sav)-min(sav))/min(sav):.1f}% spread)")
print(f"  ratio  {min(rat)}-{max(rat)}x   ({100*(max(rat)-min(rat))/min(rat):.1f}% spread)")

# the claim the report actually makes: sample size does not move the estimate
fwd = {r[1]: r[2] for r in rows if r[0].endswith("_fwd")}
if {15, 50, 100} <= set(fwd):
    drift = abs(fwd[100] - fwd[15]) / fwd[15]
    check("saving is flat across n=15/50/100 (forward sweep)", drift < 0.05, f"{100*drift:.2f}%")

print(f"\n  {'ALL CHECKS PASS' if not fails else str(len(fails)) + ' FAILURE(S)'}")
sys.exit(1 if fails else 0)
