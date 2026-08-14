#!/usr/bin/env python3
"""
Generate EVIDENCE.md — the fact-check record for this repo, block by block.

    python3 record_evidence.py

Written as a generator rather than a document, because a hand-maintained record
of "what was verified" rots exactly the way the README did: the three defects
found on 2026-08-14 were all prose that had been true before the data moved.
Re-run this and the record re-derives; it cannot quietly describe a past state.

It records WHICH blocks are machine-checked and, just as importantly, which are
not — an audit that only lists its successes is not an audit.
"""
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
README = (HERE / "README.md").read_text()


def blocks(md):
    out, cur, fence = [], [], False
    for line in md.split("\n"):
        if line.startswith("```"):
            fence = not fence
        if not line.strip() and not fence:
            if cur:
                out.append("\n".join(cur))
                cur = []
        else:
            cur.append(line)
    if cur:
        out.append("\n".join(cur))
    return out


def run(script):
    r = subprocess.run([sys.executable, str(HERE / script)], capture_output=True, text=True)
    tail = [l for l in r.stdout.strip().split("\n") if l.strip()][-1:]
    return r.returncode == 0, (tail[0].strip() if tail else "")


# Which blocks carry checkable assertions, and what covers them. Blocks not listed
# are headings, code fences, rules, or prose making no factual claim.
COVER = {
    "The claim:": ("verify_readme.py", "figures recomputed from raw per-rep data"),
    "there is no AUT here": ("verify_readme.py TOOL", "PROBE constant is `paths`"),
    "Do not quote": ("manual + parent registry", "the 55–180× retraction is real in cli-v2/README.md"),
    "real-world figure is journey-level": ("parent CLAIMS.json", "v2_effect_binary_at_real / v2_nav_effect_binary_at_real"),
    "| profile |": ("parent CLAIMS.json", "405 / 691ms registered claims"),
    "Everything here is runnable": ("verify_readme.py TOOL", "stdlib-only imports, no token"),
    "verify.py` recomputes": ("verify.py", "recomputes and fails on a hand-edited summary"),
    "verify_readme.py` fact-checks": ("verify_readme.py SELF", "checks its own stated check count"),
    "1. Fetches": ("verify_readme.py TOOL", "fetch/tempfile/rmtree present in measure.py"),
    "Your installed vibium is never modified": ("verify_readme.py TOOL", "mkdtemp + rmtree in finally"),
    "Arms are interleaved": ("verify_readme.py CONSIST", "no longer asserts the withdrawn ~3ms effect"),
    "| run | n |": ("verify_readme.py TABLE", "every row recomputed from per-rep data"),
    "Saving 107": ("verify_readme.py RANGE", "ranges and spreads recomputed"),
    "A previous sweep is kept": ("verify_readme.py COUNT", "prior rep and run counts"),
    "One claim from the earlier set": ("verify_readme.py DERIVED", "fwd/rev offset recomputed from the fresh runs"),
    "Measured on macOS": ("verify_readme.py TOOL", "meta.node_backfilled absent in results/, present in prior/"),
    "verified to apply cleanly": ("verify_readme.py EXTERNAL", "patch --dry-run against live main"),
    "It reuses the path": ("verify_readme.py CLAIM", "linkSync/renameSync and win32/isYarn present in the diff"),
    "Both guard paths are tested": ("test_guards.py", "Yarn, missing-binary, and a happy-path control"),
    "Full write-up": ("manual", "HTTP 200"),
    "Where this came from": ("manual", "LinkedIn post, quoted verbatim from the thread"),
    "Jim Evans pointed out": ("manual + live article", "`goog:channel` present in the published correction"),
    "Licence.": ("GitHub API", "repo reports MIT; vibium reports Apache-2.0"),
}

UNCHECKED_NOTE = {
    "Do not quote": "the retraction is a historical fact about the sibling project, not a live measurement",
    "Where this came from": "a third party's public comment; quoted verbatim, not independently verifiable here",
    "Jim Evans pointed out": "Firefox's BiDi behaviour is attributed to Jim Evans and explicitly not tested by us",
    "Not affiliated": "a statement of relationship, not a factual claim about the software",
}

bs = blocks(README)
rows, covered = [], 0
for i, b in enumerate(bs, 1):
    kind = ("heading" if b.startswith("#") else "code" if b.startswith("```")
            else "table" if b.startswith("|") else "rule" if b.strip() == "---" else "prose")
    hit = next((k for k in COVER if k in b), None)
    if hit:
        covered += 1
        by, ev = COVER[hit]
        note = UNCHECKED_NOTE.get(hit, "")
        rows.append((i, kind, b.split("\n")[0][:62], by, ev + (f" — {note}" if note else "")))
    else:
        rows.append((i, kind, b.split("\n")[0][:62], "—",
                     "no factual assertion" if kind in ("heading", "rule", "code") else "narrative//rationale only"))

ok_v, tail_v = run("verify.py")
ok_r, tail_r = run("verify_readme.py")
ok_g, tail_g = run("test_guards.py")

out = [f"""# Evidence record

Generated by `record_evidence.py` on {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}. Do not hand-edit —
re-run it instead. A hand-maintained record of what was verified rots exactly the
way the README did: the three defects found on 2026-08-14 were all prose that had
been true before the data moved underneath it.

## Checkers, run just now

| checker | result |
|---|---|
| `verify.py` | {'PASS' if ok_v else 'FAIL'} — {tail_v} |
| `verify_readme.py` | {'PASS' if ok_r else 'FAIL'} — {tail_r} |
| `test_guards.py` | {'PASS' if ok_g else 'FAIL'} — {tail_g} |

## Coverage

{len(bs)} blocks in README.md. {covered} carry checkable assertions and are covered below.
The remainder are headings, code fences, horizontal rules, or prose that explains
reasoning without asserting a fact.

**Four covered blocks rest partly on things this repo cannot verify**, and say so
in the table: the sibling project's retraction, a third party's public comment,
and Firefox's BiDi behaviour (attributed, explicitly untested here).

| # | kind | block | checked by | evidence |
|---|---|---|---|---|"""]
for i, kind, first, by, ev in rows:
    first = first.replace("|", "\\|")
    out.append(f"| {i} | {kind} | {first} | {by} | {ev} |")
out.append("""
## Known limits of this record

- It records that a check exists and passed, not that the check is the right one.
  `verify_readme.py`'s own rules are the thing to read if that matters.
- External claims are re-checked live where cheap (vibium's VERSION, the patch
  applying, HTTP status) and are only as current as the last run of this file.
- Absolute timings are hardware-dependent by nature. The record verifies that the
  published numbers match the stored runs, not that they will match yours.
""")
(HERE / "EVIDENCE.md").write_text("\n".join(out) + "\n")
print(f"EVIDENCE.md written — {len(bs)} blocks, {covered} with checkable assertions")
print(f"  verify.py {'PASS' if ok_v else 'FAIL'} | verify_readme.py {'PASS' if ok_r else 'FAIL'} | test_guards.py {'PASS' if ok_g else 'FAIL'}")
sys.exit(0 if (ok_v and ok_r and ok_g) else 1)
