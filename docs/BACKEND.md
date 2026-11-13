# Global register reuse and pressure scheduling — 2026-11-13

The frozen baseline is `90be4ab911d5da0fe695104d66b1f339485d827e` (compiler code `8fd5166`, successful Ubuntu run 43315024410). Development used public generated seed 129483 and direct backend seed 732619. Fresh qualification uses hold-out seed **863507**, not the earlier counted-group qualification seed 451729. Compiler timing cases remain the existing deterministic source-independent corpus.

## Proof and candidate construction

`src/global_registers.py` computes a complete backward liveness fixed point on mutable KIR. A definition interferes with every other name live after it, including when the definition itself is dead. Initial live values form a clique: this preserves implicit initial zeros, and parameter names/bindings are fixed and reserved. A dying source may share the destination because KIR reads operands before writing the result. Complete graph colouring therefore preserves the value read by every instruction on every execution, independently of timing tests. Both degree-first and saturation-first deterministic orders are offered, with copy affinity only when interference allows sharing. The palette can exceed hardware capacity; this pass adds no scratch storage or explicit spills.

A separate reaching-definition analysis splits independent lifetimes before colouring. Every original definition and initial register value has a distinct token. Forward joins union every possible reaching definition; a write replaces that register's token set. At a read, all reaching tokens are united into one def-use web. Initial webs retain their original zero/parameter binding; other webs receive fresh names. Thus every reaching definition and corresponding use has the same new name, including multiple-entry loops and joins with implicit zero values. This needs neither SSA phi instructions nor edge copies. It does not merge distinct original registers. Unreachable blocks reject the optional splitting pass.

`src/schedule.py` retains its existing RAW/WAR/WAW dependency graph, total order among potentially trapping/memory effects, fixed terminator and volatile-block exclusion. Additional priorities track versions of values rather than mutable register names, favouring last uses over births; an alternative favours bringing estimated pressure below capacity. These are profitability heuristics only. Every permutation still follows the dependency DAG, then passes the existing bounded structural path timing checks. The original latency-first scheduler remains the default in preceding stages.

`src/backend.py` offers standalone global colouring, split-web colouring, pressure schedules and selected compositions on the preceding portfolio winner. It preserves instruction/block order except when the checked scheduler supplies a permutation. The final CLI comparison starts with that preceding winner and rejects any new candidate that is slower on any available timing case. Reference/candidate step budgets, diverse RAM patterns and bounded profile weights remain unchanged. Sample checks select profitability; they do not establish legality. No filename, benchmark identity or stored answer is used.

## Bounds and limitations

The final stage runs for original inputs of 5–500 instructions, including single-block functions. Global colouring accepts at most 2,048 emitted instructions, 128 blocks and 256 names. Liveness and interference construction share a 500,000-unit budget; an incomplete analysis rejects. Reaching definitions accept at most 1,024 instructions, 128 original names and 256 resulting webs, with a separate 500,000-unit budget. Worklist propagation uses integer bit sets. Greedy colouring has bounded worst-case cubic work in the capped name count. Pressure schedules accept up to 64 nonterminal instructions per block, and retain the existing bounded path/context timing budget.

This is global reuse of proved noninterfering values, not a complete allocation backend. It has no live-range splitting with inserted transfers, physical-register assignment, rematerialization or reserved-memory spills. Static liveness overapproximates all CFG paths, so infeasible paths can block reuse. Parameters remain reserved even after their initial values die. Sampled timing cannot guarantee a speedup on every unseen input, machine or profile. Large inputs retain the prior scalable pipeline.

## Validation

The first full public pass measured **82,827 cycles**, versus 85,283 at the frozen baseline: 109 pairs improved, 391 tied, none regressed. Totals by machine: default 13,105; few registers 21,402; no fused 14,735; slow memory 21,797; wide/fast 11,788. It passed all 500 public cases and 32,000 generated comparisons with zero reference timeouts.

`tests/backend.py` directly checks both colouring orders, split webs, coloured webs, both pressure permutations before profitability filtering, backend portfolio candidates and CLI output. Its 120 fixtures across eight machines and twelve inputs pass **130,248** comparisons. Actual direct permutations occur in 1,250 blocks for each pressure mode. Fixtures cover dead writes, source/destination overlap, both branch arms, implicit zeros, mutable parameters, loop-carried values, irreducible entries, shuffled/renamed CFGs, volatile I/O, exact explicit traps and both implicit trap types. Zero reference timeouts. Eleven dedicated unit tests cover graph and reaching-definition safety boundaries; the complete unit suite has 83 tests.

Fresh hold-out seed **863507** passes 4,560 independent current-output equivalence checks, separately 4,560 baseline checks, 220 matrix-oracle checks and two-hash determinism on six unseen machine configurations. Against 90be4ab: **669 faster, 3,891 tied, zero slower**, zero reference timeouts. Matrix cycles 84,325,190→84,065,690; long streams 3,010,837→2,830,608; short streams 1,497,214→1,383,158. Maximum current compilation 0.993 seconds; baseline maximum 3.742 seconds under concurrent local test load. These maxima do not establish a compiler-throughput ratio. No compiler changes were made after inspecting this sealed result. Exact configurations/outcomes are in [the JSON report](BACKEND_HOLDOUT_2026-11-13.json).

All previous targeted suites and two stress seeds pass; local total **657,670 generated current-output comparisons**. The archived submission builds/runs from another directory, passes the external validator and has the required DESIGN headings without bundled kit directories. Ubuntu 22.04 / Python 3.10 verified code `373089912ec27947a5b598a6ff892f55c25aa62f` in **14 minutes 38 seconds**, with 83 unit tests, all 500 public cases and **652,870 generated current-output comparisons**. Public maximum 0.552 seconds; fresh hold-out maximum 1.703 seconds. The known reference/feature skips are separate from matches. [Successful CI run](https://github.com/oki-dokii/Oxygen-Debt/actions/runs/43433809633). Full handoff is in [WORKFLOW.md](WORKFLOW.md).

## Reproduce

```sh
python3 -m unittest discover -s tests
python3 tests/backend.py /path/to/LLH-26/Compilers/COMP10
python3 tests/benchmark.py /path/to/LLH-26/Compilers/COMP10 --random 64 --seed 832719
mkdir -p /tmp/oxygen-register-baseline
git archive 90be4ab | tar -x -C /tmp/oxygen-register-baseline
python3 tests/holdout.py /path/to/LLH-26/Compilers/COMP10 \
  --baseline /tmp/oxygen-register-baseline/kopt --seed 863507 --report /tmp/backend-holdout.json
```
