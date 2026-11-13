# Public submission comparison — refreshed 2026-11-13

This compares our externally validated practice results with public author reports. It is not an official leaderboard; private entries and unindexed repositories are outside the search. No competitor optimizer was built or executed, and no competitor optimizer code was incorporated. Competitors are reviewed from published documentation and reports only. All three competitor snapshots were refreshed on November 13; the preceding release passed Ubuntu verification, and the new backend release is being qualified.

## Refreshed revisions

| Entry | Revision | Evidence |
|---|---|---|
| Oxygen Debt | Global backend based on frozen `90be4ab`; final code pin pending | Independent kit runner and fresh seed 863507; current Ubuntu run pending |
| COMP10_ROKACODE | `1485b298f36e8027cd7c332949933af5b6001c7a` — unchanged in this refresh | Current README and benchmark report |
| kopt-kiln-optimizer | `24000693b889211e3fbf12fc63a2317ac00f0081` — boost4, unchanged in this refresh | Current README and boost4/boost2 benchmark report |
| ariv-IIITB/oxygen-debt | `a67f0efc7475a552f72a2bd6ec569b7616baba6d` | Rust README/DESIGN/HANDOFF; latest handoff reports 70,525 at c0e021a |

GitHub's API was used to re-fetch the three competitors' default-branch commits, READMEs, design documents and available benchmark reports. Our kit remains `d23ac1d865df4cdacf7ad8e9fff3e1d560761c46`. Public program names and reported unoptimized machine totals match, but competitor kit/input bytes have not been independently checked.

## Additional repository search

Searched GitHub repository and code indexes with forks included: `"oxygen debt" in:name,description,readme` (45 results), `"kopt" "Kiln" in:readme` (four: ours plus three peers), `"LLH-26" in:readme`, recent COMP10/KIR/kopt repositories, and distinctive machine fields in Python, Rust and C++. A language-independent `"reg_spill_penalty"` code search returned 29 files in ours, ROCA, Rust and the official kit. The organizer repository's public fork list was empty. These focused queries reported complete result sets, but GitHub indexing can lag and inaccessible/private entries are not covered. This is all discoverable relevant public entries found, not a complete submission list.

Three additional machine-field hits were checked and excluded: Dhuvie/subbyte-mcu is microcontroller quantization research, Sanbaj01/Vector-Processing-GPU-Simulation is a vector processor simulator, and diyaaaaaa790/PipSched is a MIPS pipeline teaching project. Other plausible Kiln/KIR hits were TinyML/PyTorch or Common Lisp projects.

The refreshed [Rust entry](https://github.com/ariv-IIITB/oxygen-debt/tree/a67f0efc7475a552f72a2bd6ec569b7616baba6d) has advanced substantially. Its [HANDOFF](https://github.com/ariv-IIITB/oxygen-debt/blob/a67f0efc7475a552f72a2bd6ec569b7616baba6d/HANDOFF.md) reports a final WSL sample sum of **70,525** at `c0e021a`, zero failures and 0.87-second slowest public compilation. This supersedes intermediate design figures of 83,230 and 74,369. No current five-machine breakdown or raw cycle report was found in the tree; the number is author-reported and refers to the handoff's named code revision, not an independently rerun measurement of its latest documentation commit. It is 14.9% below our sum. Its documented additions include exact-cost local scheduling/renaming, polynomial loop algebra, known bits/SCCP, state splitting, nest-aware peeling and spill reload reuse. The earlier claim that this entry had no published numeric evidence is now obsolete.

[SiddharthaReddy018/comp01](https://github.com/SiddharthaReddy018/comp01/tree/3fb386edf4bded59ee8624b01df042759b0bae32) also appeared in the event search, but it targets the COMP01 SUBLEQ self-hosting compiler problem. It is not a directly comparable Oxygen Debt entry.

## Current summed sample cycles

Lower is better. These are sums over 100 supplied sample inputs per machine, not a judging score or unseen-input prediction.

| Machine | Ours, measured | ROCA, reported | C++ peer, latest reported |
|---|---:|---:|---:|
| Default | 13,105 | Not broken down | 8,529 |
| Few registers | 21,402 | Not broken down | 13,589 |
| No fused | 14,735 | Not broken down | 10,386 |
| Slow memory | 21,797 | Not broken down | 11,993 |
| Wide/fast | 11,788 | Not broken down | 6,625 |
| All five | **82,827** | **163,533** | **51,122** |

Our sum is 49.4% below ROCA's published sum. The current C++ report is 38.3% below ours, so our sum is about 1.62 times its reported sum. This is a comparison against claims, not a reproduced head-to-head benchmark.

The old 500-row matrix JSON still sums to 52,130; the available stream report is older too (default 8,973). Neither is the new 51,122-cycle boost2 report. Therefore the old 26-wins/39-ties/435-losses count is historical and must not be presented as a comparison against the latest peer. Current aggregate values come from the refreshed README/BENCHMARKS. Boost4 expands matrix recipes to 16 columns and reduced-effort searches for larger products; its report explicitly says all 500 public pairs remain unchanged from boost2. Thus 51,122 remains the current reported public total, despite the newer commit. The Rust handoff reports 70,525 overall, without a current per-machine breakdown; it is therefore recorded separately rather than filling unknown table cells.

## What changed in our submission

Selected default sample gains versus the pre-bit-synthesis release (`a2d47f6`):

| Kernel | Before | Now |
|---|---:|---:|
| popcount | 176 | **15** |
| bit_reverse | 176 | **15** |
| crc_bitwise | 854 | **350** |
| nested_invariant | 447 | **11** |
| matmul4 | 730 | **415** |
| adler32 | 555 | **144** |
| fletcher16 | 348 | **96** |

The strongest new gains follow structural proofs, not program names: SWAR counting, GF(2) synthesis, natural-loop invariants and additive nest collapse. Wider pure specialization covers up to twelve bits over two parameters and still rejects arrays. A separate common-modulus proof now defers checksum reductions while keeping ordinary loads, trapping behavior and canonical outputs intact; this improves Adler and Fletcher without specializing memory contents.

The previous counted-group release improves ten public pairs and ties 490 against bb43e4f, with no new sample regressions. Default matvec8 improves 81→65 and row_sums 73→52; few-register matvec8 improves 253→77. Sieve keeps its previous candidate because general uncertain-trip grouping did not qualify for production. The five-machine sum is 85,283 versus 85,653 before this release. The preceding control-target wins remain: default sieve 1,608, bounds_trap 505 and branchy_select 301. See [HOLDOUT.md](HOLDOUT.md) for a fresh 76-source qualification with 1,118 faster inputs, no measured regressions, and the rejected short-loop experiment.

The latest global backend lowers the sum further, **85,283→82,827**, with 109 improved pairs, 391 ties and no measured public regressions. It adds complete mutable-register interference colouring, optional def-use web splitting and pressure scheduling as final candidates. On few registers, branchy_select improves 1,434→815 and sieve 2,352→1,939. A separate fresh qualification at seed 863507 yields 669 faster, 3,891 tied and zero slower inputs across six unseen machines. See [BACKEND.md](BACKEND.md) for proof, limits and independent tests.

## Architecture and evidence

Our mutable KIR pipeline now offers proof-based bit synthesis, bounded natural-loop LICM and additive collapse, two-parameter exhaustive specialization, and a small deterministic portfolio combining memory reuse, scheduling, allocation and unrolling choices. Profiles add bounded timing weights; they never authorize a transformation. The C++ documentation describes SSA/global analyses, a much wider candidate portfolio, stronger allocation/rematerialization/scratch choices, and broader memory/nest/matrix recipes. The remaining matrix and broader memory-loop gaps are consistent with that broader scope. The current control layer adds affine diamond conversion, guarded loop clamping with late trap restoration, pointer induction candidates and four checked copies for proved guard/address loops.

Our added tests include alternate bit widths and CRC polynomials, nonlinearity/effect rejection, direct bit outputs, nested zero-trip and dominance cases, negative/wrapping additive coefficients, twelve-bit/two-input finite domains, and unselected nested candidates. A separate suite mutates every public source with register renaming, block shuffling, 96 actual constant changes, three new machines and wrong profiles, then checks repeated output across hash seeds. Reference step-limit skips are reported separately from matches. A new checksum suite directly checks normalizers and unselected candidates, including wrapped-positive products, late-tainted raw temporaries, zero trips and load traps. Static-control fixtures additionally check plain/cached and unselected outputs for varied rectangular nests, overlapping arrays, unknown aliases, volatile I/O, effects before traps and all live counters. No stored array contents or named recipes are used. The release handoff records exact counts and Ubuntu evidence.

The peer describes extensive fuzzing, metamorphic and sanitizer campaigns. Those claims were not rerun, and counts with different definitions do not rank correctness. Our current public score is stronger than before, but the available evidence still places the latest C++ report substantially ahead. No winning claim follows from these practice measurements.

## Highest-payoff next work

These are engineering priorities inferred from our measured costs and the competitors' documented capabilities, not proof that copying a reported strategy will reproduce its gains. All implementations must be derived from semantics and keep existing candidates.

1. **Global register allocation and pressure-aware scheduling.** The new final candidate now supports cross-block interference colouring and web splitting; the preceding allocator still mainly recycles block-local names. Next investigate transfer-based splitting or rematerialization only with a corresponding proof and measured need. The C++ entry and new Rust entry describe interference colouring/coalescing, while the C++ entry also describes rematerialization and alternate scheduling directions. The gap to the C++ report is largest in absolute cycles on slow memory (21,797 versus 11,993, gap 9,804) and few registers (21,402 versus 13,589, gap 7,813). The first bounded interference/pressure step is implemented; do not rewrite the entire compiler into SSA just to follow another architecture. Scratch spills require proof that original accesses cannot touch the reserved region.
2. **Extend the counted-loop proof cautiously.** The new production stage handles guaranteed-long memory loops with factors 2/4/8, signed overshoot proofs and a scalar tail. Uncertain/short-loop prototypes caused penalties and are not offered by the CLI. The fresh qualification improved larger matrices/long streams without a measured loss. Further coverage of short or uncertain trips needs a better cost/entry strategy, not simply relaxing the current gate; the grouping gate itself remains unchanged (the later backend improves few-register sieve).
3. **Matrix operand sharing and small tiles.** Our expansion removes control but does not systematically share a loaded operand across several output accumulators or neighbouring rows. Current directly comparable matmul4 reports are below. Prove complete in-bounds ranges and disjoint output/input storage before changing load/store order. Try small column chunks and retain current order for overlap/trap cases. The confirmed matmul gap is 1,117 cycles across five machines, so this is a focused win rather than an explanation of the full 31,705-cycle gap.
4. **Load forwarding across joins and nested iterations.** Extend the current single-body rolling-load proof to joins and conditional inner loops, with versions for memory and explicit store invalidation. Our bubble_sort plus insertion_sort cost 9,077 cycles across machines. Sieve lookahead may also help, but only after proving that intervening marking stores cannot alias the prefetched flag. Wrong profiles must not affect legality.
5. **Multi-output branch/state-machine regions.** The latest affine pass handles one escaped result. vending_fsm plus dfa_dispatch still cost 5,525 cycles across machines. A bounded pure-region/finite-state proof could remove larger dispatch trees while retaining volatile access and trap ordering. Afterwards, inspect region-level GF(2) lowering and bounded histogram counters as narrower follow-ups, rather than repeating already strong popcount/reversal work.

6. **Large-program optimization quality, alongside runtime.** The official rules explicitly include roughly 100,000-instruction inputs. Our existing large check establishes speed and determinism, not broad optimization effectiveness on large live workloads. Add large live CFGs, high-fan-in joins, irreducible loops, long arithmetic/memory kernels and instruction-cache pressure; measure input/output cycles as well as compilation time. Our expensive portfolio is capped at 500 input instructions, so determine which scalable cleanups and hot-region transformations still run beyond that cap. Do not assume the public 500-pair sum predicts these cases. Claims about their exact scoring weight in a peer's notes are not independently verified organizer guidance.

| matmul4 sample | Ours measured | C++ current reported | Difference |
|---|---:|---:|---:|
| Default | 415 | 175 | 240 |
| Few registers | 507 | 453 | 54 |
| No fused | 571 | 426 | 145 |
| Slow memory | 856 | 363 | 493 |
| Wide/fast | 258 | 73 | 185 |

The C++ values are explicitly in the current boost4 report; its public inputs were not independently rerun. Other historical per-case JSON remains historical. Our largest current costs include sieve 9,303, bubble_sort 5,539, insertion_sort 3,538, vending_fsm 2,960, bounds_trap 2,939, branchy_select 2,104, matmul4 2,587, dfa_dispatch 2,565. These are absolute costs, not estimates of removable cycles.

The bounded allocation/scheduling step and fresh qualification are complete. Next pursue sorting/nested memory reuse and small matrix chunks, while checking large live-program effectiveness. Keep each change only after a measured benefit and fresh semantic qualification; preserve the verified release as fallback. Avoid starting a full SSA rewrite today.

Keep Python for now. The preceding Ubuntu public maximum was 0.576 seconds; the new local public/hold-out maxima are 0.302/0.993 seconds while Ubuntu verification is pending; a language port would consume time without directly improving emitted Kiln code. The requested fresh held-out qualification is complete. Any further tuning needs a new untouched qualification seed. Before submission, verify the clean-clone build, required DESIGN headings, deterministic output, executable/LF files, organizer access and demo/reproduction instructions.

## Sources

- [Our latest handoff and CI evidence](WORKFLOW.md)
- [ROCA README](https://github.com/RohitKattimani/COMP10_ROKACODE/blob/1485b298f36e8027cd7c332949933af5b6001c7a/README.md) and [benchmark report](https://github.com/RohitKattimani/COMP10_ROKACODE/blob/1485b298f36e8027cd7c332949933af5b6001c7a/BENCHMARK_REPORT.md)
- [Latest C++ README](https://github.com/wildwolf07/kopt-kiln-optimizer/blob/24000693b889211e3fbf12fc63a2317ac00f0081/README.md) and [boost4/boost2 benchmark report](https://github.com/wildwolf07/kopt-kiln-optimizer/blob/24000693b889211e3fbf12fc63a2317ac00f0081/BENCHMARKS.md)
- [Historical matrix data](https://github.com/wildwolf07/kopt-kiln-optimizer/blob/24000693b889211e3fbf12fc63a2317ac00f0081/results/matrix-sample-cycles.json), retained as older-stage evidence
- [Latest Rust README](https://github.com/ariv-IIITB/oxygen-debt/blob/a67f0efc7475a552f72a2bd6ec569b7616baba6d/README.md) and [design](https://github.com/ariv-IIITB/oxygen-debt/blob/a67f0efc7475a552f72a2bd6ec569b7616baba6d/DESIGN.md)
- [Latest Rust handoff and final reported total](https://github.com/ariv-IIITB/oxygen-debt/blob/a67f0efc7475a552f72a2bd6ec569b7616baba6d/HANDOFF.md)
- [Official hidden-case and submission rules](https://github.com/rudra-shroff06/LLH-26/blob/d23ac1d865df4cdacf7ad8e9fff3e1d560761c46/Compilers/COMP10/RULES_AND_SUBMISSION.md)
