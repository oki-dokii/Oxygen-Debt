# Public submission comparison — refreshed 2026-11-12

This compares our externally validated practice results with public author reports. It is not an official leaderboard; private entries and unindexed repositories are outside the search. No competitor optimizer was built or executed, and no competitor optimizer code was incorporated. The new Rust entry is reviewed from its published documentation only.

## Refreshed revisions

| Entry | Revision | Evidence |
|---|---|---|
| Oxygen Debt | `298a1ca09e6a3e142886e56ef0ea939b84ed3ff3` | [Verified Ubuntu run](https://github.com/oki-dokii/Oxygen-Debt/actions/runs/43275266030), independent kit runner and generated suites |
| COMP10_ROKACODE | `1485b298f36e8027cd7c332949933af5b6001c7a` — unchanged in this refresh | Current README and benchmark report |
| kopt-kiln-optimizer | `24000693b889211e3fbf12fc63a2317ac00f0081` — advanced to boost4 | Current README and boost4/boost2 benchmark report |
| ariv-IIITB/oxygen-debt — newly found | `85b761c9278762b335626a5ee22cfaad585403ed` | Rust README/DESIGN; no comparable cycle table found |

GitHub's API was used to re-fetch the three competitors' default-branch commits, READMEs, design documents and available benchmark reports. Our kit remains `d23ac1d865df4cdacf7ad8e9fff3e1d560761c46`. Public program names and reported unoptimized machine totals match, but competitor kit/input bytes have not been independently checked.

## Additional repository search

Searched GitHub repository and code indexes for Oxygen Debt, COMP10/Kiln, kopt/Kiln, LLH-26, KIR, recent repositories named kopt, and Oxygen Debt forks. The specific kopt/Kiln README search returned our entry plus ROCA, wildwolf07 and the newly found ariv-IIITB entry. Broad COMP10 searches contain thousands of unrelated course repositories; only the first 100 broad results were examined, so that query is not exhaustive. Specific challenge queries were also used. Other plausible Kiln/KIR hits were checked and excluded as TinyML/PyTorch compiler or Common Lisp projects. Search coverage does not include inaccessible private or unindexed submissions.

The new [ariv-IIITB/oxygen-debt](https://github.com/ariv-IIITB/oxygen-debt/tree/85b761c9278762b335626a5ee22cfaad585403ed) is a direct COMP10 entry written in Rust. Its design documents pruned SSA, dominator value numbering, ranges, memory forwarding, peeling, if-conversion, scheduling, register colouring/coalescing, scratch spills and measured configuration search. Its own missing-work list includes induction-variable strength reduction, sum reassociation, partial redundancy elimination, loop closed forms and load/store phis. This is broader backend infrastructure than ours in some areas, but the README/tree provided no comparable published cycle report. It cannot be placed above or below us by performance from this evidence.

[SiddharthaReddy018/comp01](https://github.com/SiddharthaReddy018/comp01/tree/3fb386edf4bded59ee8624b01df042759b0bae32) also appeared in the event search, but it targets the COMP01 SUBLEQ self-hosting compiler problem. It is not a directly comparable Oxygen Debt entry.

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

Our sum is 47.6% below ROCA's published sum. The current C++ report is 40.3% below ours, so our sum is about 1.68 times its reported sum. This is a comparison against claims, not a reproduced head-to-head benchmark.

The old 500-row matrix JSON still sums to 52,130; the available stream report is older too (default 8,973). Neither is the new 51,122-cycle boost2 report. Therefore the old 26-wins/39-ties/435-losses count is historical and must not be presented as a comparison against the latest peer. Current aggregate values come from the refreshed README/BENCHMARKS. Boost4 expands matrix recipes to 16 columns and reduced-effort searches for larger products; its report explicitly says all 500 public pairs remain unchanged from boost2. Thus 51,122 remains the current reported public total, despite the newer commit. The new Rust entry has no comparable number and is deliberately absent from this numeric table.

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

## Highest-payoff next work

These are engineering priorities inferred from our measured costs and the competitors' documented capabilities, not proof that copying a reported strategy will reproduce its gains. All implementations must be derived from semantics and keep existing candidates.

1. **Global register allocation and pressure-aware scheduling.** Our current allocator mainly recycles names within blocks and pins values live across edges. The C++ entry and new Rust entry describe interference colouring/coalescing, while the C++ entry also describes rematerialization and alternate scheduling directions. The gap to the C++ report is largest in absolute cycles on slow memory (22,010 versus 11,993, gap 10,017) and few registers (23,338 versus 13,589, gap 9,749). Begin with interference-safe coalescing and pressure-based priorities; do not rewrite the entire compiler into SSA just to follow another architecture. Scratch spills require proof that original accesses cannot touch the reserved region.
2. **Counted-loop groups with a scalar tail.** Four checked copies still execute a comparison per iteration. Sieve alone consumes 9,716 cycles across five machines (11.3% of our total). Prove enough remaining iterations, positive stride and no signed wrap to execute a 2/4/8-body group with fewer tests, then retain the original scalar exit path. This should target address/counting loops generally. Preserve every memory/volatile effect and predicate live-out, including on early traps.
3. **Matrix operand sharing and small tiles.** Our expansion removes control but does not systematically share a loaded operand across several output accumulators or neighbouring rows. Current directly comparable matmul4 reports are below. Prove complete in-bounds ranges and disjoint output/input storage before changing load/store order. Try small column chunks and retain current order for overlap/trap cases. The confirmed matmul gap is 1,117 cycles across five machines, so this is a focused win rather than an explanation of the full 34,531-cycle gap.
4. **Load forwarding across joins and nested iterations.** Extend the current single-body rolling-load proof to joins and conditional inner loops, with versions for memory and explicit store invalidation. Our bubble_sort plus insertion_sort cost 9,087 cycles across machines. Sieve lookahead may also help, but only after proving that intervening marking stores cannot alias the prefetched flag. Wrong profiles must not affect legality.
5. **Multi-output branch/state-machine regions.** The latest affine pass handles one escaped result. vending_fsm plus dfa_dispatch still cost 5,603 cycles across machines. A bounded pure-region/finite-state proof could remove larger dispatch trees while retaining volatile access and trap ordering. Afterwards, inspect region-level GF(2) lowering and bounded histogram counters as narrower follow-ups, rather than repeating already strong popcount/reversal work.

| matmul4 sample | Ours measured | C++ current reported | Difference |
|---|---:|---:|---:|
| Default | 415 | 175 | 240 |
| Few registers | 507 | 453 | 54 |
| No fused | 571 | 426 | 145 |
| Slow memory | 856 | 363 | 493 |
| Wide/fast | 258 | 73 | 185 |

The C++ values are explicitly in the current boost4 report; its public inputs were not independently rerun. Other historical per-case JSON remains historical. Our largest current costs are sieve 9,716, bubble_sort 5,539, insertion_sort 3,548, vending_fsm 3,017, bounds_trap 2,939, branchy_select 2,779, matmul4 2,607 and dfa_dispatch 2,586. These are absolute costs, not estimates of removable cycles.

Keep Python for now. Our latest Ubuntu public maximum is 0.377 seconds and the current compiler meets the measured runtime gates; a language port would consume time without directly improving emitted Kiln code. Reserve a final independent held-out pass covering 8–16-sized/rectangular matrices, overlap, zero/short loops, other machines and incorrect profiles before freezing the submission.

## Sources

- [Our latest handoff and CI evidence](WORKFLOW.md)
- [ROCA README](https://github.com/RohitKattimani/COMP10_ROKACODE/blob/1485b298f36e8027cd7c332949933af5b6001c7a/README.md) and [benchmark report](https://github.com/RohitKattimani/COMP10_ROKACODE/blob/1485b298f36e8027cd7c332949933af5b6001c7a/BENCHMARK_REPORT.md)
- [Latest C++ README](https://github.com/wildwolf07/kopt-kiln-optimizer/blob/24000693b889211e3fbf12fc63a2317ac00f0081/README.md) and [boost4/boost2 benchmark report](https://github.com/wildwolf07/kopt-kiln-optimizer/blob/24000693b889211e3fbf12fc63a2317ac00f0081/BENCHMARKS.md)
- [Historical matrix data](https://github.com/wildwolf07/kopt-kiln-optimizer/blob/24000693b889211e3fbf12fc63a2317ac00f0081/results/matrix-sample-cycles.json), retained as older-stage evidence
- [New Rust README](https://github.com/ariv-IIITB/oxygen-debt/blob/85b761c9278762b335626a5ee22cfaad585403ed/README.md) and [design](https://github.com/ariv-IIITB/oxygen-debt/blob/85b761c9278762b335626a5ee22cfaad585403ed/DESIGN.md)
