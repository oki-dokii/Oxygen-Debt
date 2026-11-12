# Public submission comparison — refreshed 2026-11-12

This compares our externally validated practice results with public author reports. It is not an official leaderboard; private entries and unindexed repositories are outside the search. Neither peer optimizer was built or executed, and no peer optimizer code was incorporated.

## Refreshed revisions

| Entry | Revision | Evidence |
|---|---|---|
| Oxygen Debt | `298a1ca09e6a3e142886e56ef0ea939b84ed3ff3` | [Verified Ubuntu run](https://github.com/oki-dokii/Oxygen-Debt/actions/runs/43275266030), independent kit runner and generated suites |
| COMP10_ROKACODE | `1485b298f36e8027cd7c332949933af5b6001c7a` — unchanged when re-fetched | Current README and benchmark report |
| kopt-kiln-optimizer | `761489fe765ee9a6960da8cf58f9aa716d783ef8` — updated since the previous comparison | Refreshed README and boost2 benchmark report |

GitHub's API was used to re-fetch both main commits and READMEs. Our kit remains `d23ac1d865df4cdacf7ad8e9fff3e1d560761c46`. Public program names and reported unoptimized machine totals match, but competitor kit/input bytes have not been independently checked.

## Current summed sample cycles

Lower is better. These are sums over 100 supplied sample inputs per machine, not a judging score or unseen-input prediction.

| Machine | Ours, measured | ROCA, reported | C++ peer, latest reported |
|---|---:|---:|---:|
| Default | 13,285 | Not broken down | 8,529 |
| Few registers | 23,338 | Not broken down | 13,589 |
| No fused | 14,888 | Not broken down | 10,386 |
| Slow memory | 22,010 | Not broken down | 11,993 |
| Wide/fast | 12,132 | Not broken down | 6,625 |
| All five | **85,653** | **163,533** | **51,122** |

Our sum is 47.6% below ROCA's published sum. The latest C++ report is 40.3% below ours, so our sum is about 1.68 times its reported sum. This is a comparison against claims, not a reproduced head-to-head benchmark.

The old 500-row matrix JSON still sums to 52,130; the available stream report is older too (default 8,973). Neither is the new 51,122-cycle boost2 report. Therefore the old 26-wins/39-ties/435-losses count is historical and must not be presented as a comparison against the latest peer. Current aggregate values come from the refreshed README/BENCHMARKS, whose boost2 table reports additional matrix-product recipes.

## What changed in our submission

Selected default sample gains versus the pre-bit-synthesis release (`a2d47f6`):

| Kernel | Before | Now |
|---|---:|---:|
| popcount | 176 | **15** |
| bit_reverse | 176 | **15** |
| crc_bitwise | 854 | **386** |
| nested_invariant | 447 | **11** |
| matmul4 | 730 | **415** |
| adler32 | 555 | **151** |
| fletcher16 | 348 | **101** |

The strongest new gains follow structural proofs, not program names: SWAR counting, GF(2) synthesis, natural-loop invariants and additive nest collapse. Wider pure specialization covers up to twelve bits over two parameters and still rejects arrays. A separate common-modulus proof now defers checksum reductions while keeping ordinary loads, trapping behavior and canonical outputs intact; this improves Adler and Fletcher without specializing memory contents.

The remaining-target step improves all 15 target/machine pairs and ties the other 485 against `89b6f34`, with no new sample regressions. Default sieve improves 1,702→1,608, bounds_trap 901→505 and branchy_select 345→301. The five-machine sum is 85,653 versus 88,736 before this release. The preceding historical portfolio tradeoffs remain recorded in D-030; no current sample is slower than its unoptimized input. Rankings still use bounded timing cases, with a separate control round adding long zero-RAM, all-one and alternating cases while retaining the existing portfolio winner.

## Architecture and evidence

Our mutable KIR pipeline now offers proof-based bit synthesis, bounded natural-loop LICM and additive collapse, two-parameter exhaustive specialization, and a small deterministic portfolio combining memory reuse, scheduling, allocation and unrolling choices. Profiles add bounded timing weights; they never authorize a transformation. The C++ documentation describes SSA/global analyses, a much wider candidate portfolio, stronger allocation/rematerialization/scratch choices, and broader memory/nest/matrix recipes. The remaining matrix and broader memory-loop gaps are consistent with that broader scope. The current control layer adds affine diamond conversion, guarded loop clamping with late trap restoration, pointer induction candidates and four checked copies for proved guard/address loops.

Our added tests include alternate bit widths and CRC polynomials, nonlinearity/effect rejection, direct bit outputs, nested zero-trip and dominance cases, negative/wrapping additive coefficients, twelve-bit/two-input finite domains, and unselected nested candidates. A separate suite mutates every public source with register renaming, block shuffling, 96 actual constant changes, three new machines and wrong profiles, then checks repeated output across hash seeds. Reference step-limit skips are reported separately from matches. A new checksum suite directly checks normalizers and unselected candidates, including wrapped-positive products, late-tainted raw temporaries, zero trips and load traps. Static-control fixtures additionally check plain/cached and unselected outputs for varied rectangular nests, overlapping arrays, unknown aliases, volatile I/O, effects before traps and all live counters. No stored array contents or named recipes are used. The release handoff records exact counts and Ubuntu evidence.

The peer describes extensive fuzzing, metamorphic and sanitizer campaigns. Those claims were not rerun, and counts with different definitions do not rank correctness. Our current public score is stronger than before, but the available evidence still places the latest C++ report substantially ahead. No winning claim follows from these practice measurements.

## Sources

- [Our latest handoff and CI evidence](WORKFLOW.md)
- [ROCA README](https://github.com/RohitKattimani/COMP10_ROKACODE/blob/1485b298f36e8027cd7c332949933af5b6001c7a/README.md) and [benchmark report](https://github.com/RohitKattimani/COMP10_ROKACODE/blob/1485b298f36e8027cd7c332949933af5b6001c7a/BENCHMARK_REPORT.md)
- [Latest C++ README](https://github.com/wildwolf07/kopt-kiln-optimizer/blob/761489fe765ee9a6960da8cf58f9aa716d783ef8/README.md) and [boost2 benchmark report](https://github.com/wildwolf07/kopt-kiln-optimizer/blob/761489fe765ee9a6960da8cf58f9aa716d783ef8/BENCHMARKS.md)
- [Historical matrix data](https://github.com/wildwolf07/kopt-kiln-optimizer/blob/761489fe765ee9a6960da8cf58f9aa716d783ef8/results/matrix-sample-cycles.json), retained as older-stage evidence
