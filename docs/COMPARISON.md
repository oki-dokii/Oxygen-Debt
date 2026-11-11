# Public submission comparison — 2026-11-12

This is a comparison with public documentation and published result data, not an official leaderboard. Search found two other repositories implementing this exact COMP10 challenge. Private entries and unindexed repositories are not covered. A COMP01 self-hosting compiler and unrelated projects named Kiln were excluded.

## Revisions and evidence

| Entry | Revision | Evidence used |
|---|---|---|
| Oxygen Debt | `040642d` (code `d149226`) | Our external-kit runner and successful Ubuntu verification |
| COMP10_ROKACODE | `1485b298f36e8027cd7c332949933af5b6001c7a` | Public README, DESIGN, and benchmark report |
| kopt-kiln-optimizer | `1689c93ce8ae4629914aef090bf2a097e31b66c9` | Public README, DESIGN, BENCHMARKS, and 500-row sample-cycle JSON |

We did not build or execute the competitor optimizers. Their numbers and test outcomes remain author-reported. No competitor optimizer code was copied or incorporated. The peer documentation was fetched through GitHub's API because web search did not index all relevant pages.

Our results use organizer kit `d23ac1d865df4cdacf7ad8e9fff3e1d560761c46`, all 100 supplied programs, five supplied machines, and their sample inputs. The reported original totals match ours; this supports comparison but does not establish byte-identical kit revisions or input files for the competitors.

## Sample-cycle comparison

Lower is better. These are sums of supplied sample cycles, not a judging score or a hidden-input prediction.

| Machine | Oxygen Debt, independently measured | ROCA, reported | kopt-kiln-optimizer, reported |
|---|---:|---:|---:|
| Default | 16,645 | Not broken down in its report | 8,700 |
| Few registers | 31,190 | Not broken down in its report | 13,846 |
| No fused | 19,070 | Not broken down in its report | 10,403 |
| Slow memory | 25,703 | Not broken down in its report | 12,372 |
| Wide/fast | 16,808 | Not broken down in its report | 6,809 |
| All five | **109,416** | **163,533** | **52,130** |

Our total is 33.1% lower than ROCA's published total. The C++ competitor's published total is 52.4% lower than ours: our sum is about 2.10 times theirs. Its default-machine sum is 47.7% lower than ours. These calculations compare our measurements with their claims; they are not an independently reproduced head-to-head benchmark.

The C++ repository's published JSON contains exactly 500 matching program/machine keys and sums to its README totals. Compared with those rows, our optimizer is faster in 26 pairs, ties 39, and is slower in 435. Its reported sample outputs are never slower than the original sample timings recorded by our runner; our sample outputs also have zero original-input regressions. Neither observation guarantees performance on a different input.

| Default-machine example | Ours | C++ peer, reported |
|---|---:|---:|
| collatz | **18** | 511 |
| sum_sq | 13 | **8** |
| matmul4 | 730 | **316** |
| crc_bitwise | 854 | **250** |
| nested_invariant | 447 | **16** |
| adler32 | 555 | **126** |
| bubble_sort | 920 | **515** |
| bit_reverse | 176 | **15** |
| popcount | 176 | **14** |

ROCA reports default `sum_sq` at 21 cycles and `matmul4` at 1,018, versus our 13 and 730. Our specialization produces strong wins on some bounded pure computations; the remaining gap spans many workloads.

## Architecture and validation

| Area | Oxygen Debt | ROCA documentation | C++ competitor documentation |
|---|---|---|---|
| Representation | Mutable KIR blocks, ranges, local values and liveness | Mutable blocks and greedy register coloring | SSA with global analyses and lowering |
| Scheduling | Bounded dependency scheduling; additional spill contexts and a fixed timing budget | Not implemented | Forward, backward, pressure-aware and tree-ordering alternatives |
| Registers | Local name reuse and short-cycle guards | Global greedy coloring | Multiple allocation/coalescing alternatives, rematerialization and guarded scratch spilling |
| Loops and memory | Bounded polynomial formulas, hoisting, short doubling, local load reuse and safe store cleanup | Narrow square-sum and induction recognizers | Broader loop plans, unswitching, cross-iteration load reuse/pipelining, and matrix-related reuse |
| Pure computations | Exhaustive specialization after proving at most ten masked bits | Narrow algebraic recognizers | Finite-domain proofs plus bit-demand and bit-affine alternatives |
| Profiles | Edge-based block layout | Accepted but ignored | Profile-guided candidate ranking and layout |
| Selection | Mostly one pass trajectory; limited formula/lookup alternatives | Mostly one pass trajectory | Broad deterministic candidate portfolio |

Our Ubuntu workflow reproduced the build, 42 unit tests, demo, 500 public pairs, 32,000 generated comparisons, 4,800 stress comparisons, and 222,400 targeted comparisons. A second local stress seed adds 4,800 comparisons, giving 264,000 generated comparisons locally. The scheduling suite now checks that changed programs actually exercise loops and traps. Its earlier oversized random blocks were outside the scheduler's limit; that coverage gap was corrected.

ROCA reports 500 successful pairs with 100 additional randomized inputs, focused regressions, and 100,000-instruction / 1,000-live-register tests. The C++ report describes 3,000 fuzz programs, 500 metamorphic programs, sanitizer campaigns, generated transformation fixtures, and 1,200 unseen-machine checks. We have not reproduced these campaigns. Test counts and definitions differ, so the counts alone cannot rank correctness. We cannot claim stronger correctness coverage than the C++ entry on this evidence.

## Priorities inferred from the gaps

1. Improve global loop and memory optimization: induction/address simplification, provable cross-iteration load reuse, and broader invariant removal. `matmul4`, `sieve`, sorting and stencil kernels are useful independent test families.
2. Add proven bit-operation and affine-expression synthesis for popcount, bit reversal and CRC-like workloads. Derive transformations from semantics and source structure, with independently generated tests.
3. Explore a small deterministic candidate portfolio with register-pressure-aware allocation/scheduling. Retain unchanged candidates and measure on inputs separated from any profitability inputs.
4. Expand end-to-end metamorphic checks: rename registers, shuffle blocks, vary constants, change machines, and provide misleading profiles across many complete programs.

The reports suggest we are ahead of the narrower ROCA implementation in these sample totals and behind the strongest public implementation found. A winning claim requires independent reproduction and, ultimately, the organizers' unseen tests.

## Sources

- [Our successful Ubuntu run](https://github.com/oki-dokii/Oxygen-Debt/actions/runs/43081525052)
- [ROCA README](https://github.com/RohitKattimani/COMP10_ROKACODE/blob/1485b298f36e8027cd7c332949933af5b6001c7a/README.md), [benchmark report](https://github.com/RohitKattimani/COMP10_ROKACODE/blob/1485b298f36e8027cd7c332949933af5b6001c7a/BENCHMARK_REPORT.md), [design](https://github.com/RohitKattimani/COMP10_ROKACODE/blob/1485b298f36e8027cd7c332949933af5b6001c7a/DESIGN.md)
- [C++ README](https://github.com/wildwolf07/kopt-kiln-optimizer/blob/1689c93ce8ae4629914aef090bf2a097e31b66c9/README.md), [benchmark report](https://github.com/wildwolf07/kopt-kiln-optimizer/blob/1689c93ce8ae4629914aef090bf2a097e31b66c9/BENCHMARKS.md), [500-row sample results](https://github.com/wildwolf07/kopt-kiln-optimizer/blob/1689c93ce8ae4629914aef090bf2a097e31b66c9/results/matrix-sample-cycles.json), [design](https://github.com/wildwolf07/kopt-kiln-optimizer/blob/1689c93ce8ae4629914aef090bf2a097e31b66c9/DESIGN.md)
