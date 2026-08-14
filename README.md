# vibium-cli-startup-repro

Reproduction material for a proposed change to the `vibium` npm package: resolve
`bin` to the platform binary at install time, instead of shipping a Node script
that re-execs it.

Everything here is runnable. Nothing requires access to the author's machine, a
GitHub token, or any third-party Python package.

**The claim:** every `vibium <verb>` currently costs two process spawns — Node
boots, resolves a path, then execs the real binary. That is a near-constant
~107ms, and it is avoidable. On our hardware, removing it takes a `vibium paths`
call from ~118ms to ~10ms.

**The honest caveat:** absolute numbers are hardware- and load-dependent. Expect
different milliseconds. The **ratio** (~11.6×–11.9× on this probe) is the portable
part, and the method below is designed so you can check the effect against your
own machine's noise rather than trusting ours.

---

## Run it yourself

Requires `python3`, `node`, `npm`, and an installed `vibium`. Two minutes.

```bash
git clone https://github.com/lana-20/vibium-cli-startup-repro
cd vibium-cli-startup-repro

python3 measure.py 50 mine        # n=50, results written to results/n50_mine.json
```

It will print something like:

```
vibium main VERSION 26.5.31 · fixtures from /usr/local/lib/node_modules/vibium
  shim    bin/cli.js -> a /usr/bin/env node script text executable
  patched bin/cli.js -> Mach-O 64-bit executable x86_64

  shim    median   118.4 ms  (sd 1.9)
  patched median    10.0 ms  (sd 0.3)
  saving           108.4 ms   11.88x
  noise floor        3.1 ms median, 13.9 max
  correctness    50/50 byte-identical, 0 mismatches
```

If `vibium` is not on the global npm root, point at it:

```bash
VIBIUM_PACKAGE_DIR=/path/to/node_modules/vibium python3 measure.py 50 mine
```

## Check our numbers without running anything

```bash
python3 verify.py
```

This recomputes every published figure from the stored per-rep data in
`results/`. It does not trust the summary blocks — editing one by hand makes it
fail. Verified by doing exactly that.

---

## What `measure.py` actually does

1. Fetches `packages/vibium/bin/cli.js`, `packages/vibium/postinstall.js` and
   `VERSION` **from vibium's `main`, at run time.** So it measures current code,
   and it fails loudly if the patch no longer applies rather than silently
   measuring an unpatched build.
2. Makes two throwaway copies of your installed vibium package and drops those
   sources in. Applies the patch to one copy only.
3. Runs each copy's `postinstall`, then times both through an npm-style
   `.bin/vibium` symlink — because invoking the file by path changes `argv0`,
   and that is not how anyone runs it.
4. Writes results to `results/` and deletes the fixtures.

**Your installed vibium is never modified.** Both fixtures live in a temp
directory that is removed on exit, including on failure.

### Why the method looks paranoid

Because the first version of this measurement was wrong, and the paranoia is
what caught it.

- **Arms are interleaved**, one rep each with alternating order — never
  all-A-then-all-B. Our first sweep ran n=15, then 50, then 100 in that order and
  appeared to show the saving growing with sample size. It wasn't: the machine was
  getting busier, and `n` was confounded with elapsed time. Re-running the sweep
  in reverse separated them. The estimate is flat across n; the ~3ms difference
  is machine state.
- **Every rep is correctness-checked**, not just timed. stdout must match the
  shim's byte for byte and the exit code must match. A faster wrong answer is not
  a saving. Across 380 reps here: **zero mismatches**.
- **A noise floor is measured** by timing the *same* arm twice per rep. That is a
  control the change cannot possibly have affected, so it tells you what your
  machine produces when nothing happened. Our saving is ~37× that floor. If
  yours isn't comfortably above it, the effect isn't there on your hardware and
  we'd like to know.
- **Results are written to disk.** A figure with no stored output is one nobody
  can check.

---

## What's here

| path | what it is |
|---|---|
| `measure.py` | the harness. Run it. |
| `verify.py` | recomputes our published figures from raw per-rep data |
| `patch/postinstall.diff` | the proposed change, as a unified diff against `main` |
| `results/*.json` | our runs: n=15/50/100, each sweep also run in reverse, plus one replication |

`results/` filenames: `n<N>_fwd` and `n<N>_rev` are the forward and reverse
sweeps; `n50_run1` is an earlier independent n=50 kept as a replication check.
The harness refuses to overwrite an existing result file — pass a label instead.
That guard exists because an unlabelled re-run destroyed its own first pass here,
turning a set of summaries into figures nobody could check.

## Our results

7 runs, 380 scored reps, 0 correctness mismatches.

| run | n | saving | ratio | noise floor |
|---|---|---|---|---|
| n15_fwd | 15 | 108.4ms | 11.92× | 3.0ms |
| n50_fwd | 50 | 108.4ms | 11.88× | 3.1ms |
| n100_fwd | 100 | 108.9ms | 11.92× | 2.9ms |
| n15_rev | 15 | 111.6ms | 11.87× | 4.4ms |
| n50_rev | 50 | 110.9ms | 11.61× | 2.2ms |
| n100_rev | 100 | 111.9ms | 11.70× | 2.4ms |
| n50_run1 | 50 | 107.4ms | 11.77× | 1.9ms |

Saving 107.4–111.9ms (4.2% spread), ratio 11.61×–11.92× (2.7% spread). Sample
size moves the estimate by 0.46%; sweep direction moves it by 2.8%.

Measured on macOS x86_64, Node v25.8.0, against vibium `main` at VERSION 26.5.31.

## The patch

`patch/postinstall.diff` — verified to apply cleanly to `main` as of 2026-08-14.

It reuses the path `postinstall.js` already resolves (`getVibiumBinPath()` is
duplicated verbatim between `postinstall.js` and `bin/cli.js`), and hard-links
the platform binary over the shim: `linkSync` then an atomic `renameSync`. That
is esbuild's mechanism, with esbuild's guards — Windows, Yarn and any error skip
the optimization and leave the Node shim exactly as it is today, including its
`Could not find vibium binary for <platform>-<arch>` message.

Both guard paths are tested, not just the happy one.

## Context

**Full write-up**, including the journey-level measurements and the risks:
https://daisyladybug.com/blog/making-vibium-cli-faster/

**Where this came from.** The write-up was posted to LinkedIn on 2026-08-13:
https://www.linkedin.com/feed/update/urn:li:activity:7493779001782530048/

In the comments, Jason Huggins wrote: *"we should probably file 'skip the wrapper'
as an enhancement/bug and fix that directly. thanks for running the analysis!"* —
which is why this repo exists. It is a request to file, not an endorsement of the
particular patch here; the patch and its risks are mine to defend.

The same thread produced a correction worth repeating: Jim Evans pointed out that
tagging subscriptions with the channel that created them is a **Chromium** extension
(`goog:channel`), not something WebDriver BiDi requires, and that Firefox's current
BiDi does not carry the field. The article has been corrected. It does not affect
anything measured here — this repo times process startup, not protocol behaviour —
but it is the reason the write-up now scopes its subscription findings to Chromium.

Not affiliated with the Vibium project. Offered in the spirit of "here is the
measurement, here is the patch, here is how to check both."
