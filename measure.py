#!/usr/bin/env python3
"""
Reproduce: does replacing the npm Node shim with a hard link to the platform
binary actually save ~107ms per `vibium` invocation?

    python3 measure.py [n] [label]        default n=50

Standalone. Needs python3, node, npm, and an installed `vibium`. No auth, no
third-party packages, nothing from the author's machine.

WHAT IT DOES

Builds two throwaway copies of your installed vibium package, drops in
`bin/cli.js` and `postinstall.js` **as they are on vibium's `main` right now**,
applies the proposed patch to one copy only, runs each copy's postinstall, then
times both through an npm-style `.bin/vibium` symlink.

Nothing installed on your machine is modified. Both fixtures live in a temp
directory that is removed on exit.

WHY IT IS BUILT THIS WAY

  * The patch does not exist upstream, so the only honest way to put a number on
    it is to apply it to current sources and measure.
  * **Arms are interleaved** one rep at a time with alternating order, never
    all-A-then-all-B. Machine load drifts; blocked arms turn drift into a fake
    effect.
  * **Every rep is correctness-checked**, not just timed. stdout must match the
    shim's byte for byte and the exit code must match. A faster wrong answer is
    not a saving.
  * A **noise floor** is measured by timing the *same* arm twice per rep, so the
    reported effect can be compared against what your machine produces when
    nothing changed at all.
  * Results are written to disk. A figure with no stored output is one nobody
    can check.

EXPECT DIFFERENT ABSOLUTE NUMBERS THAN OURS. Node startup cost is hardware- and
load-dependent. The ratio is the portable part.
"""
import json
import os
import platform
import shutil
import statistics as st
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "results"
RAW = "https://raw.githubusercontent.com/VibiumDev/vibium/main/{}"
PROBE = "paths"        # pure CLI work: no browser, no network, no daemon state


def fetch(path):
    """Current source straight from vibium's main. No auth, no gh CLI.

    Falls back to curl because a python.org Python on macOS ships without a CA
    bundle and urllib raises CERTIFICATE_VERIFY_FAILED -- which would otherwise
    make this script fail on a very common setup for reasons unrelated to vibium.
    """
    url = RAW.format(path)
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return r.read().decode()
    except Exception:
        pass
    try:
        r = subprocess.run(["curl", "-fsSL", url], capture_output=True, text=True, timeout=60)
        if r.returncode == 0 and r.stdout:
            return r.stdout
        err = r.stderr.strip() or f"curl exit {r.returncode}"
    except FileNotFoundError:
        err = "curl not found either"
    sys.exit(f"could not fetch {path} from vibium main: {err}")


def find_installed():
    """Locate the installed vibium package portably."""
    env = os.environ.get("VIBIUM_PACKAGE_DIR")
    if env:
        p = Path(env)
        if (p / "package.json").exists():
            return p
        sys.exit(f"VIBIUM_PACKAGE_DIR={env} has no package.json")
    try:
        root = subprocess.run(["npm", "root", "-g"], capture_output=True,
                              text=True, timeout=60).stdout.strip()
    except Exception:
        root = ""
    for cand in ([Path(root) / "vibium"] if root else []) + [
            Path("/usr/local/lib/node_modules/vibium"),
            Path.home() / ".npm-global/lib/node_modules/vibium"]:
        if (cand / "package.json").exists() and (cand / "bin").exists():
            return cand
    sys.exit("could not find an installed vibium package.\n"
             "  install it (`npm i -g vibium`) or set VIBIUM_PACKAGE_DIR=/path/to/node_modules/vibium")


PATCH_FUNCS = '''
function isYarn() {
  const { npm_config_user_agent } = process.env;
  return !!npm_config_user_agent && /\\byarn\\//.test(npm_config_user_agent);
}

function maybeReplaceShimWithBinary(vibiumPath) {
  if (os.platform() === 'win32') return 'skipped: win32';
  if (isYarn()) return 'skipped: yarn';
  const shimPath = path.join(__dirname, 'bin', 'cli.js');
  const tempPath = `${shimPath}.${process.pid}.tmp`;
  try {
    if (!fs.statSync(vibiumPath).isFile()) return 'skipped: binary not a file';
    fs.linkSync(vibiumPath, tempPath);
    fs.renameSync(tempPath, shimPath);
    return 'linked';
  } catch (err) {
    try { fs.unlinkSync(tempPath); } catch {}
    return `skipped: ${err.code || err.message}`;
  }
}
'''


def apply_patch(post_src):
    """The proposed change, applied to main's postinstall.js. Fails loudly if
    upstream has moved, rather than silently measuring an unpatched build."""
    out = post_src
    dep = "const { execFileSync } = require('child_process');"
    if dep not in out:
        sys.exit("postinstall.js no longer requires execFileSync -- re-derive the patch")
    out = out.replace(dep, dep + "\nconst fs = require('fs');")
    anchor = "try {\n  const vibiumPath = getVibiumBinPath();"
    if anchor not in out:
        sys.exit("postinstall.js shape changed upstream -- re-derive the patch")
    out = out.replace(anchor, PATCH_FUNCS + "\n" + anchor)
    call = "  execFileSync(vibiumPath, ['install'], { stdio: 'inherit' });"
    if call not in out:
        sys.exit("postinstall.js install call changed -- re-derive the patch")
    return out.replace(call, call + "\n  const outcome = maybeReplaceShimWithBinary(vibiumPath);\n"
                       "  if (outcome !== 'linked') console.log(`vibium: keeping the Node shim (${outcome})`);")


def build(base, name, installed, cli_src, post_src, patched):
    pkg = base / name
    shutil.copytree(installed, pkg, symlinks=True)
    (pkg / "bin" / "cli.js").write_text(cli_src)
    (pkg / "postinstall.js").write_text(apply_patch(post_src) if patched else post_src)
    subprocess.run(["node", "postinstall.js"], cwd=pkg, capture_output=True)
    d = base / f"bin_{name}"
    d.mkdir(exist_ok=True)
    link = d / "vibium"
    if link.exists() or link.is_symlink():
        link.unlink()
    link.symlink_to(pkg / "bin" / "cli.js")
    kind = subprocess.run(["file", "-b", str(pkg / "bin" / "cli.js")],
                          capture_output=True, text=True).stdout.strip()
    return str(link), kind


def timed(cmd):
    t = time.perf_counter()
    r = subprocess.run([cmd, PROBE], capture_output=True)
    return (time.perf_counter() - t) * 1000, r.stdout, r.returncode


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 50
    label = sys.argv[2] if len(sys.argv) > 2 else ""
    OUT.mkdir(exist_ok=True)
    out_file = OUT / (f"n{n}_{label}.json" if label else f"n{n}.json")
    if out_file.exists():
        sys.exit(f"{out_file.name} exists -- pass a label instead of overwriting it")

    installed = find_installed()
    cli_src, post_src = fetch("packages/vibium/bin/cli.js"), fetch("packages/vibium/postinstall.js")
    version_main = fetch("VERSION").strip()
    print(f"vibium main VERSION {version_main} · fixtures from {installed}")

    base = Path(tempfile.mkdtemp(prefix="vibium_repro_"))
    try:
        shim, k1 = build(base, "shim", installed, cli_src, post_src, False)
        patched, k2 = build(base, "patched", installed, cli_src, post_src, True)
        print(f"  shim    bin/cli.js -> {k1[:44]}")
        print(f"  patched bin/cli.js -> {k2[:44]}")
        if "executable" not in k2 or "script" in k2:
            sys.exit("the patched fixture did not become a native binary -- aborting rather "
                     "than reporting a meaningless comparison")

        ref_out = subprocess.run([shim, PROBE], capture_output=True).stdout
        rows, mismatches = [], 0
        for i in range(n):
            order = ["shim", "patched"] if i % 2 == 0 else ["patched", "shim"]
            rec = {"rep": i + 1, "first": order[0]}
            for arm in order:
                ms, out, rc = timed(shim if arm == "shim" else patched)
                rec[f"{arm}_ms"] = round(ms, 3)
                rec[f"{arm}_ok"] = (out == ref_out and rc == 0)
                if not rec[f"{arm}_ok"]:
                    mismatches += 1
            rec["shim_again_ms"] = round(timed(shim)[0], 3)
            rows.append(rec)
            if (i + 1) % 25 == 0:
                print(f"  {i+1}/{n}")

        good = [r for r in rows if r["shim_ok"] and r["patched_ok"]]
        if not good:
            sys.exit("no rep passed the correctness check -- not reporting timings")
        s = [r["shim_ms"] for r in good]
        p = [r["patched_ms"] for r in good]
        floor = [abs(r["shim_again_ms"] - r["shim_ms"]) for r in good]
        summary = {
            "n_requested": n, "n_scored": len(good), "correctness_mismatches": mismatches,
            "probe": f"vibium {PROBE}",
            "shim": {"median": round(st.median(s), 1), "mean": round(st.mean(s), 1),
                     "stdev": round(st.pstdev(s), 1)},
            "patched": {"median": round(st.median(p), 1), "mean": round(st.mean(p), 1),
                        "stdev": round(st.pstdev(p), 1)},
            "saving_median_ms": round(st.median(s) - st.median(p), 1),
            "ratio_median": round(st.median(s) / st.median(p), 2),
            "noise_floor_median_ms": round(st.median(floor), 1),
            "noise_floor_max_ms": round(max(floor), 1),
            "main_version": version_main,
        }
        out_file.write_text(json.dumps({
            "summary": summary, "per_rep": rows,
            "meta": {"measured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                     "platform": f"{platform.system().lower()}-{platform.machine()}",
                     "python": platform.python_version(),
                     "node": subprocess.run(["node", "-v"], capture_output=True, text=True).stdout.strip(),
                     "vibium_main_version": version_main,
                     "measures": "a proposed patch, not shipped code"}}, indent=2) + "\n")

        print(f"\n  shim    median {summary['shim']['median']:>7} ms  (sd {summary['shim']['stdev']})")
        print(f"  patched median {summary['patched']['median']:>7} ms  (sd {summary['patched']['stdev']})")
        print(f"  saving         {summary['saving_median_ms']:>7} ms   {summary['ratio_median']}x")
        print(f"  noise floor    {summary['noise_floor_median_ms']:>7} ms median, {summary['noise_floor_max_ms']} max")
        print(f"  correctness    {len(good)}/{n} byte-identical, {mismatches} mismatches")
        print(f"\n  -> {out_file}")
    finally:
        shutil.rmtree(base, ignore_errors=True)


if __name__ == "__main__":
    main()
