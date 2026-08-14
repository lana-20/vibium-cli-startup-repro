#!/usr/bin/env python3
"""
Exercise the patch's guard paths, not just the happy one.

    python3 test_guards.py

The patch deliberately declines to optimize in cases where replacing a file in
place is not clearly safe, and falls back to leaving the Node shim exactly as it
is. A fallback nobody has triggered is a fallback nobody knows works, so each
path is built and run here rather than asserted in prose:

  * Yarn        -- Yarn's linker moves package files around, so in-place
                   replacement is not reliable. esbuild skips Yarn for the same
                   reason.
  * no binary   -- the platform package is absent. The shim must survive AND
                   keep printing its own clear error, which is the specific
                   regression an install-time link could otherwise cause.
  * happy path  -- the control. If this did not link, the other two proving
                   "shim retained" would mean nothing.

Nothing installed on your machine is modified; fixtures are temporary.
"""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import measure

fails = []


def check(label, cond, detail=""):
    print(f"  {'ok  ' if cond else 'FAIL'}  {label}" + (f"   [{detail}]" if detail else ""))
    if not cond:
        fails.append(label)


def build(base, name, env=None, drop_binary=False):
    """A patched fixture, with the environment or layout under test."""
    installed = measure.find_installed()
    pkg = base / name
    shutil.copytree(installed, pkg, symlinks=True)
    (pkg / "bin" / "cli.js").write_text(CLI)
    (pkg / "postinstall.js").write_text(measure.apply_patch(POST))
    if drop_binary:
        shutil.rmtree(pkg / "node_modules" / "@vibium", ignore_errors=True)
    r = subprocess.run(["node", "postinstall.js"], cwd=pkg, capture_output=True, text=True,
                       env={**__import__("os").environ, **(env or {})})
    kind = subprocess.run(["file", "-b", str(pkg / "bin" / "cli.js")],
                          capture_output=True, text=True).stdout.strip()
    return pkg, kind, r.stdout + r.stderr


print("fetching current sources from vibium main…")
CLI = measure.fetch("packages/vibium/bin/cli.js")
POST = measure.fetch("packages/vibium/postinstall.js")

base = Path(tempfile.mkdtemp(prefix="vibium_guards_"))
try:
    print("\n1. happy path — the control")
    pkg, kind, out = build(base, "happy")
    check("bin/cli.js becomes a native binary", "executable" in kind and "script" not in kind, kind[:38])
    check("it still runs", subprocess.run([str(pkg / "bin" / "cli.js"), "paths"],
                                          capture_output=True).returncode == 0)

    print("\n2. Yarn — must decline and say so")
    pkg, kind, out = build(base, "yarn", env={"npm_config_user_agent": "yarn/1.22.19 npm/? node/v24"})
    check("shim left as a Node script", "script" in kind, kind[:38])
    check("declines out loud", "keeping the Node shim" in out and "yarn" in out,
          next((l for l in out.split("\n") if "keeping" in l), "")[:52])
    check("shim still runs", subprocess.run([str(pkg / "bin" / "cli.js"), "--version"],
                                            capture_output=True).returncode == 0)

    print("\n3. platform binary absent — the regression that matters")
    pkg, kind, out = build(base, "nobin", drop_binary=True)
    check("shim left as a Node script", "script" in kind, kind[:38])
    r = subprocess.run([str(pkg / "bin" / "cli.js"), "paths"], capture_output=True, text=True)
    check("today's clear error is preserved",
          "Could not find vibium binary" in (r.stdout + r.stderr),
          (r.stdout + r.stderr).strip()[:52])
finally:
    shutil.rmtree(base, ignore_errors=True)

print(f"\n  {'ALL PASS' if not fails else str(len(fails)) + ' FAILURE(S): ' + ', '.join(fails)}")
sys.exit(1 if fails else 0)
