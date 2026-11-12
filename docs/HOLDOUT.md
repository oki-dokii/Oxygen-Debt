# Independent hold-out qualification — 2026-11-13

The previous verified compiler was frozen at `bb43e4f` (compiler code `298a1ca`, Ubuntu run [43275266030](https://github.com/oki-dokii/Oxygen-Debt/actions/runs/43275266030)). The baseline is copied with `git archive`, so edits to the working tree cannot change it. The immutable baseline tag is `baseline-before-counted-groups-2026-11-13`.

## What is new

The sealed qualification uses seed **451729**, separate from the compiler timing corpus, previous generated suites and the development experiment. It contains 76 renamed/shuffled source instances: 30 rectangular/large matrix products, 30 short/signed/effectful streams, and 16 streams whose bounds have a proved positive minimum. Matrix shapes include 8×8×8, 16×16×16, 3×11×7, 7×2×13, zero rows/columns/depth and overlapping input/output storage. The streams cover group boundaries, variable strides, negative bounds, unknown aliases, volatile input, division and explicit/implicit traps.

Six machine configurations use 4/5/7/11/19/31 registers, different issue widths, memory ports, cache sizes, spill/branch costs, latencies and all fused-feature combinations. These configurations were not used to choose compiler candidates. Most source instances receive intentionally misleading exit-heavy profiles; some omit profiles. RAM patterns include zero, all-one words, signed boundary stripes, sparse words and fresh random words. Every compiled output is repeated under two different Python hash seeds.

## Results

- 4,560 current outputs match the independent external organizer VM; zero reference timeouts or compiler failures.
- The frozen baseline independently matches all 4,560 references too; these extra baseline checks are not added to the current-compiler match count.
- 220 returning matrix inputs also match a separate mathematical oracle, including sequential aliasing and the preheader RAM write.
- New versus frozen timing: **1,118 faster, 3,442 tied, 0 slower** input/machine pairs.
- Matrix cycles: **84,329,310 → 81,949,440** (2.82% fewer).
- Guaranteed-long stream cycles: **4,203,814 → 3,087,549** (26.55% fewer).
- Short/signed stream cycles: **1,543,797 → 1,543,797**, unchanged.
- Maximum measured compiler wall time: 0.562 seconds current, 0.321 seconds baseline. These maxima do not establish a compiler-throughput ratio or guarantee judging-host time.

The machine configuration details, outcomes and exact totals are in [the JSON report](HOLDOUT_2026-11-13.json). These totals describe this new corpus, not an official score. The large products dominate the aggregate and must not be mistaken for the public 500-pair metric.

## What the development run rejected

The initial experiment at seed 932617 passed equivalence but introduced setup costs on short loops, including an 80→205-cycle zero-trip case. Deferring setup removed the zero-trip setup, but some one-iteration cases still lost substantially. Those unconstrained candidates are **not offered by the production CLI**.

Production grouping now requires a statically guaranteed first complete group, positive invariant stride and signed nonwrap/overshoot proofs. Its separate timing stage retains the previous winner and rejects any candidate slower on even one timing case. The general entry-guarded form remains covered by direct proof tests, but production does not speculate that an unknown trip count will be large. The compiler and these policies were fixed before evaluating the fresh seed 451729; the sealed results were not used to tune them.

## Reproduce

```sh
mkdir -p /tmp/oxygen-counted-baseline
git archive bb43e4f | tar -x -C /tmp/oxygen-counted-baseline
python3 tests/holdout.py /path/to/LLH-26/Compilers/COMP10 \
  --baseline /tmp/oxygen-counted-baseline/kopt \
  --seed 451729 --report /tmp/holdout.json
```

`--baseline` is optional for pure correctness/determinism qualification. Every reference must finish within the explicit one-million-step limit; a reference timeout fails rather than being counted as a pass. Semantic differences and compiler failures save a reproducer under `--artifacts` (default `/tmp/oxygen-holdout-failure`). Public and older generated suites are separate gates recorded in [WORKFLOW](WORKFLOW.md).
