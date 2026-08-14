# Prior run set — kept, not replaced

The first sweep, run 2026-08-14. Superseded as the headline evidence by the runs in
`results/`, which were measured fresh with the published `measure.py`. Kept because
deleting a run set makes the fresh one unfalsifiable: two independent sessions
agreeing is stronger evidence than one session asserted twice.

7 runs, 380 scored reps, 0 correctness mismatches.
Saving 107.4–111.9ms, ratio 11.61×–11.92×.

**One claim from this set did not replicate.** These runs showed the reverse sweep
landing ~2.9ms above the forward sweep, and the README explained it as machine state.
In the fresh set the offset is −0.2ms — no systematic direction effect at all. So the
+2.9ms was a property of that session, not of sweep order, and the README no longer
claims otherwise. That is the whole reason this directory still exists.

`node` in these files is `node_backfilled: true`; the harness that produced them did
not capture it. The fresh runs record it live.
