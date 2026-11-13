# Cross-block load forwarding — 2026-11-13

The frozen baseline is `439106e` (compiler code `3730899`, verified Ubuntu run 43433809633). It is archived outside the working tree. Development used public generated seed 742193 and direct fixture seed 618427. Fresh qualification uses **927641**, with the optional larger signed-sorting corpus enabled. The compiler's own timing cases are unchanged.

## Memory facts and proof

`src/forwarding.py` tracks two kinds of facts: affine register equalities and ordinary memory equations `memory[address] = holder`. Expressions use up to four current register roots with coefficients/constants modulo 2^32. It handles constants, copies, addition/subtraction, constant products/shifts and affine fused operations. Unsupported arithmetic drops the equality. RAM contents are never read during this proof.

A successful ordinary load or store establishes a memory equation. A store invalidates every possibly aliasing cached address. Equal coefficient vectors with different constants are disjoint modulo 2^32; all other address pairs may alias. No store is removed. A register write removes that register as a value holder. Address/equality facts depending on the old register value are dropped unless the assignment has an odd coefficient for the overwritten root. Such an assignment is bijective modulo 2^32: substituting its modular inverse rewrites equations in terms of the new root. Even/noninvertible writes drop dependent facts. This does not assume signed arithmetic cannot wrap.

Before a CFG join, current affine equalities can express the same cached address through another register. For example, a predecessor knowing `i=1` can express its fact about address 1 as a fact about address i. At a join, only equal aliases and address/holder equations present on **every** incoming edge survive. Unvisited back edges supply empty facts, not optimistic facts. Function entry always has an empty state, including if entry has a back edge. The pass requires its budgeted worklist to settle before emitting changes.

A load becomes a copy/constant only when this must-available equation proves its value at that exact point. The previous successful access also proves the address is valid. Removing the later read therefore preserves its value and cannot remove a possible trap. Unknown aliases, overwritten holders and unproved address changes invalidate reuse. Volatile ports have separate state in KIR; their original instructions/operands remain in place, and volatile loads still invalidate their destination. Return/trap values, data memory and ordered volatile history remain unchanged.

## Conditional suppliers and first iteration

When all predecessors know a memory value at the same current address but hold it in different registers, the optional `join_copies` primitive assigns a fresh common register on each predecessor. These are pure copies/constants before the existing terminator; they cannot trap or alter original registers. Executing a fresh copy on an untaken edge is harmless. Entry joins are excluded, and fresh names are selected from unused legal names even when the input uses v999999. Reanalysis can then discover the common memory equation. Copies alone never authorize load removal.

`src/peeling.py` distinguishes the first iteration of a bounded natural loop by CFG duplication. The region must have a sole external entry at its header; removing header back edges must leave a DAG. The original region serves the first iteration. All original back edges enter the copied header; copied internal edges refer to copied blocks, and exits retain their targets. This is exactly the original sequence of instructions on every execution, including zero trips, early exits, traps and live-out counters. Nothing is moved before an entry test.

After duplication, must-available analysis can retain a value supplied by the preceding iteration on all paths into the copied loop. The first iteration keeps its original read; later iterations may use a proved carry. This supports conditional swap/supplier paths without speculating an initial load on a zero-trip path. The implementation does not recognize benchmark names or sorting algorithms.

## Integration and bounds

A separate final CLI round starts from the established backend winner. It tries forwarding on the original source and that winner, then optional common holders/first-iteration copies. Each result can undergo the existing cleanup and backend candidate generation. The original winner is the first timing candidate, and every new output must avoid losses on every available timing case. Profiles remain bounded profitability hints; timing checks never establish the memory proof.

Original inputs must contain 5–500 instructions. Analysis accepts at most 2,048 emitted instructions and 128 blocks, with a 400,000-unit budget shared across fixed-point propagation and final rewriting. States retain at most 128 aliases and 32 cached addresses; dropping a fact is conservative. Expressions exceeding four roots are dropped. Each source offers at most one direct and two peeled alternatives. Common holders are capped at four per source. Peeling accepts at most 1,024 instructions and 64 blocks; each copied region has at most 12 blocks/128 instructions, and at most two regions are offered. Greedy structural scans, bounded set operations and copied CFG size determine cost. Budget exhaustion rejects the optional candidate.

This is not full memory SSA or general PRE. Nonaffine address equivalence, relational inequalities, noninvertible rebasing and arbitrary cyclic/multiple-entry regions remain conservative. Extra copies, code size and register pressure can lose on unseen inputs despite sampled nonregression. Existing candidates remain available. Large programs retain the preceding scalable pipeline.

## Validation

The public matrix passes all 500 cases and 32,000 generated comparisons, with no reference timeouts. The five-machine sum is **82,827 → 81,730**: 31 pairs improve, 469 tie and none regress against the frozen baseline. Totals: 12,911 default; 21,395 few-register; 14,637 no-fused; 21,125 slow-memory; 11,662 wide/fast. Maximum local public compilation is 0.639 seconds under concurrent test load.

Selected sample improvements: default bubble sort 810→722, insertion sort 550→522 and merge 288→252; slow-memory insertion sort 1,158→906 and merge 536→380. These names occur only in tests/reports, never optimizer recognition.

`tests/forwarding.py` passes **85,120** direct/join/peeled/composed/cleaned/CLI comparisons on 136 fixtures and eight machines, plus **256 mathematical signed-sorting oracle checks**. Direct pairs remove 1,328 load instructions in aggregate. Cases include renamed/shuffled nested loops, conditional suppliers, zero/short trips, early exits, unknown alias stores, overwritten holders, self-overwriting addresses, modular odd/even coefficients, volatile I/O and effects before load/division traps. Every reference finishes; none is counted as a pass after timing out. Fourteen new unit tests bring the total to 97.

Fresh hold-out seed **927641** contains 92 renamed/shuffled sources on six unseen machines with wrong/absent profiles, ten inputs and two hash seeds per current output. It includes sixteen larger signed-sorting programs (31/63 masks, fresh bases), alongside the existing larger/overlapping matrix and effectful-stream families. All **5,520** current outputs match the independent VM, as do separately 5,520 frozen-baseline outputs. There are **220 matrix and 160 signed-sorting oracle checks**, zero reference timeouts and no determinism failures.

Timing versus frozen 439106e: **709 faster, 4,783 tied, 28 slower**. Sorting totals **53,357,980→49,610,457** (7.02% fewer); matrices **77,345,020→77,344,510**; long/short streams unchanged at 2,791,973 / 1,350,567. Worst relative regression: short sorting input 3 on unseen_7, **327→362** (35 cycles, 10.70%). Worst absolute regression: sorting input 127 on unseen_7, **172,879→181,439** (8,560 cycles, 4.95%). These are retained, disclosed tradeoffs; no compiler or timing-corpus change was made after inspecting qualification. Sampled nonregression does not imply unseen-input nonregression. The measured sorting aggregate gain is retained, not presented as universal dominance. A future budget-aware extension of profitability cases could address the residual risk, but requires another untouched qualification.

A targeted replay of both worst cases reproduces the exact cycle counts without changing the compiler. In the largest loss, loads fall 7,812→3,969, but 11,655 moves appear; dynamic instructions rise 43,539→51,225, static instructions 26→46 and named registers 8→9. That machine has seven registers, a 37-instruction cache, spill penalty 11 and cache penalty 1. This supports copy/register/cache pressure as a cause of the loss, without isolating each modeled cost. Future copy coalescing/identity-copy removal and profitability-budget work should be evaluated with another untouched seed. [Exact replay counts](FORWARDING_REGRESSION_AUDIT_2026-11-13.json).

Maximum current/baseline compilation: 0.861/3.304 seconds under concurrent local load; these maxima do not establish a throughput ratio. Exact machine configurations and worst cases are in [the JSON report](FORWARDING_HOLDOUT_2026-11-13.json). The preexisting backend and all older targeted/mutation suites plus two stress seeds also pass locally: **743,750 generated current-output comparisons**. The expanded demo includes both sorting kernels and merge. Five representative/large outputs pass two-hash determinism and output-only/build/executable/LF checks; the 100,001-instruction case takes at most 0.570 seconds locally. Code `b637236364d9050ae5f3df6177ac76b0bc4e6578` passes [Ubuntu verification](https://github.com/oki-dokii/Oxygen-Debt/actions/runs/43462303399): 97 unit tests, all 500 public cases and **738,950 generated current-output comparisons** across core/loop/memory jobs. The longest job takes 12m42s. Public maximum compilation is 0.730 seconds; fresh hold-out maximum is below 2.021 seconds. Known reference/feature skips remain separately reported. CI checks correctness/determinism; the local frozen-baseline timings above retain the 28 disclosed losses. [Full handoff](WORKFLOW.md).

## Reproduce

```sh
python3 -m unittest discover -s tests
python3 tests/forwarding.py /path/to/LLH-26/Compilers/COMP10
python3 tests/benchmark.py /path/to/LLH-26/Compilers/COMP10 --random 64 --seed 832719
mkdir -p /tmp/oxygen-forwarding-baseline
git archive 439106e | tar -x -C /tmp/oxygen-forwarding-baseline
python3 tests/holdout.py /path/to/LLH-26/Compilers/COMP10 \
  --sorting --baseline /tmp/oxygen-forwarding-baseline/kopt \
  --seed 927641 --report /tmp/forwarding-holdout.json
```
