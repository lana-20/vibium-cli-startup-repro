#!/usr/bin/env python3
"""
Fact-check the README against this repo's own contents.

    python3 verify_readme.py

`verify.py` checks that our published figures recompute from the raw per-rep
data. This checks the README's *prose* — every number in it, every structural
claim about the tooling, and its internal consistency.

It exists because a paragraph-by-paragraph audit on 2026-08-14 found three
defects that neither the reader nor `verify.py` would have caught:

  * a bullet still asserting a "~3ms machine state" direction effect that a
    later section of the same README explicitly withdrew,
  * "across 380 reps here" after the current set became 330 (380 was the
    superseded session),
  * a file table describing `n50_run1` as if it were still in `results/` after
    it moved to `results/prior/`.

All three were internal contradictions: the README disagreeing with itself or
with its own directory. Those are exactly what a human skim misses and a
mechanical check does not.

Claims about the outside world (vibium's version, the patch applying, the
journey figures) are marked EXTERNAL and re-checked live where cheap.
"""
import json
import re
import statistics as st
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
README = (HERE / "README.md").read_text()
RESULTS = {f.stem: json.loads(f.read_text()) for f in (HERE / "results").glob("n*.json")}
PRIOR = {f.stem: json.loads(f.read_text()) for f in (HERE / "results/prior").glob("n*.json")}

fails, checked = [], 0


def check(kind, label, cond, evidence=""):
    global checked
    checked += 1
    print(f"  {'ok  ' if cond else 'FAIL'} [{kind}] {label}")
    if evidence:
        print(f"        {evidence}")
    if not cond:
        fails.append(label)


S = {k: v["summary"] for k, v in RESULTS.items()}
P = {k: v["summary"] for k, v in PRIOR.items()}

print("1. Every figure in the results table recomputes from raw per-rep data")
for name, blob in sorted(RESULTS.items()):
    s, reps = blob["summary"], blob["per_rep"]
    good = [r for r in reps if r.get("shim_ok") and r.get("patched_ok")]
    sav = st.median([r["shim_ms"] for r in good]) - st.median([r["patched_ms"] for r in good])
    row = re.search(rf"\|\s*{re.escape(name)}\s*\|\s*(\d+)\s*\|\s*([\d.]+)ms\s*\|\s*([\d.]+)×\s*\|\s*([\d.]+)ms\s*\|", README)
    check("TABLE", f"{name} row matches raw data",
          bool(row) and abs(float(row.group(2)) - sav) < 0.15 and int(row.group(1)) == len(good),
          f"raw saving {sav:.1f}ms over {len(good)} scored reps")

print("\n2. Stated ranges and totals")
sav = [v["saving_median_ms"] for v in S.values()]
rat = [v["ratio_median"] for v in S.values()]
allsav = sav + [v["saving_median_ms"] for v in P.values()]
allrat = rat + [v["ratio_median"] for v in P.values()]
reps_now = sum(v["n_scored"] for v in S.values())
reps_all = reps_now + sum(v["n_scored"] for v in P.values())
check("RANGE", "current saving range", f"{min(sav)}–{max(sav)}ms" in README, f"{min(sav)}–{max(sav)}ms")
check("RANGE", "current ratio range", f"{min(rat)}×–{max(rat)}×" in README, f"{min(rat)}×–{max(rat)}×")
check("RANGE", "combined saving range", f"{min(allsav)}–{max(allsav)}ms" in README, f"{min(allsav)}–{max(allsav)}ms")
check("RANGE", "combined ratio range", f"{min(allrat)}×–{max(allrat)}×" in README, f"{min(allrat)}×–{max(allrat)}×")
check("COUNT", "current rep count", f"{reps_now} scored reps" in README, f"{reps_now}")
check("COUNT", "combined rep count", f"{reps_all} reps" in README, f"{reps_all}")
check("COUNT", "run counts", f"{len(S)} runs" in README and f"{len(S)+len(P)} runs" in README,
      f"{len(S)} current, {len(S)+len(P)} total")

print("\n3. Derived figures")
drift = 100 * abs(S["n100_fwd"]["saving_median_ms"] - S["n15_fwd"]["saving_median_ms"]) / S["n15_fwd"]["saving_median_ms"]
check("DERIVED", "sample-size drift", f"{drift:.2f}%" in README, f"{drift:.2f}%")
mult = [v["saving_median_ms"] / v["noise_floor_median_ms"] for v in S.values()]
check("DERIVED", "noise-floor multiple", f"{min(mult):.0f}×–{max(mult):.0f}×" in README,
      f"{min(mult):.0f}×–{max(mult):.0f}×")
f = st.mean([S[f"n{n}_fwd"]["saving_median_ms"] for n in (15, 50, 100)])
r = st.mean([S[f"n{n}_rev"]["saving_median_ms"] for n in (15, 50, 100)])
# Normalise the minus sign: prose uses U+2212 MINUS, format() emits U+002D HYPHEN.
# The first version of this check failed on that alone and briefly looked like a
# README defect -- a checker's own encoding assumptions are part of the checker.
_norm = lambda t: t.replace("\u2212", "-")
check("DERIVED", "withdrawn direction effect stated as measured",
      f"{r-f:.1f}ms" in _norm(README), f"fresh fwd/rev offset {r-f:+.1f}ms")

print("\n4. Internal consistency — the class that caused all three known defects")
check("CONSIST", "no bullet still asserts the withdrawn ~3ms direction effect",
      "~3ms difference" not in README,
      "a later section withdraws it; both cannot stand")
check("CONSIST", "no stale rep count from the superseded session",
      "380 reps here" not in README, "380 is results/prior/, not results/")
check("CONSIST", "n50_run1 is described where it actually lives",
      (HERE / "results/prior/n50_run1.json").exists() and not (HERE / "results/n50_run1.json").exists()
      and "results/prior/` holds the earlier session" in README,
      "file is in results/prior/")
check("CONSIST", "sample output block matches a real stored run",
      all(str(S["n50_fwd"][k] if not isinstance(S["n50_fwd"][k], dict) else S["n50_fwd"][k]["median"]) in README
          for k in ("saving_median_ms", "shim", "patched")),
      "block reproduces n50_fwd")

print("\n5. Structural claims about the tooling")
src = (HERE / "measure.py").read_text() + (HERE / "verify.py").read_text()
imports = set(re.findall(r"^\s*(?:import|from)\s+([a-zA-Z_][\w.]*)", src, re.M))
stdlib = {"json", "os", "platform", "shutil", "statistics", "subprocess", "sys", "tempfile",
          "time", "urllib", "urllib.request", "datetime", "pathlib", "re", "argparse"}
check("TOOL", "no third-party Python package", not imports - stdlib, f"imports {sorted(imports)}")
check("TOOL", "no GitHub token or gh CLI needed", "gh api" not in src and "GITHUB_TOKEN" not in src,
      "fetches from raw.githubusercontent.com")
mp = (HERE / "measure.py").read_text()
check("TOOL", "probe is `vibium paths`, drives no page", 'PROBE = "paths"' in mp, "PROBE constant")
check("TOOL", "installed vibium never modified",
      "mkdtemp" in mp and "rmtree" in mp and "finally:" in mp, "temp fixtures, rmtree in finally")
check("TOOL", "harness refuses to overwrite a result file", "pass a label" in mp, "out_file.exists() guard")
check("TOOL", "fresh runs capture node live; prior are backfilled",
      all(not v["meta"].get("node_backfilled") for v in RESULTS.values())
      and all(v["meta"].get("node_backfilled") for v in PRIOR.values()),
      "meta.node_backfilled absent in results/, present in results/prior/")

print("\n6. EXTERNAL — re-checked live")
try:
    ver = subprocess.run(["curl", "-fsSL", "https://raw.githubusercontent.com/VibiumDev/vibium/main/VERSION"],
                         capture_output=True, text=True, timeout=30).stdout.strip()
    check("EXTERNAL", "vibium main VERSION matches the README", ver and ver in README, f"main is {ver}")
    pi = subprocess.run(["curl", "-fsSL", "https://raw.githubusercontent.com/VibiumDev/vibium/main/packages/vibium/postinstall.js"],
                        capture_output=True, text=True, timeout=30).stdout
    tmp = HERE / ".pi_check.js"
    tmp.write_text(pi)
    r = subprocess.run(["patch", "-s", "--dry-run", str(tmp)],
                       stdin=(HERE / "patch/postinstall.diff").open(), capture_output=True, text=True)
    tmp.unlink()
    check("EXTERNAL", "patch still applies cleanly to main", r.returncode == 0, r.stderr.strip()[:80] or "clean")
except Exception as e:
    print(f"  skip [EXTERNAL] network checks unavailable: {e}")

print(f"\n  {checked} checks, {'ALL PASS' if not fails else str(len(fails)) + ' FAILURE(S): ' + ', '.join(fails)}")
sys.exit(1 if fails else 0)
