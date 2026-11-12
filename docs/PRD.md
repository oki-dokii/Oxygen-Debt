# Product requirements

Build a command-line optimizer that takes a KIR program and a Kiln machine configuration, then writes a valid KIR program that produces the same observable results with fewer simulated cycles where we can find a safe improvement.

The judges need a reproducible build, the exact command they specify, and an optimizer that works on unseen programs. The team needs a quick way to check each pass, see what it changed, and explain why the change is valid.

| Priority | Scope | Evidence |
|---|---|---|
| Required | End-to-end `kopt` command, legal output on the specified machine, and deterministic output | Clean build and CLI smoke test, with and without a profile |
| First optimization milestone | Constant folding, copy propagation, safe arithmetic simplification, and dead pure computation removal | Small positive and negative tests plus measured improvements on public workloads |
| Competitive milestone | Redundant arithmetic removal and machine-dependent fusion, followed by register reuse or scheduling where measurements justify it | Same-input cycle comparisons across public machines and workloads |
| Stretch | Conservative block layout using profile weights or safe loop improvements | Gains on multiple workloads, with equivalence checks and an analysis of regressions |

The competitive milestone now includes polynomial loop elimination, bounded dependency scheduling, proved cross-iteration memory reuse, and exhaustive specialization after proving a small input domain. Preserve usefulness on unseen programs through structural proofs and generated tests with renamed registers, changed constants, and negative cases. Keep the private repository's current validation evidence and known limits in the handoff; stronger public samples alone do not establish winning performance.

Treat any semantic mismatch, invalid output, or timeout as a failed case. Track the number of programs improved, unchanged, or slower alongside cycle changes, and record optimizer runtime separately from simulated cycles. Publish measured results with the machine, input, and commit identified.

The [SRS](SRS.md) defines release checks. The [workflow](WORKFLOW.md) defines what to run after each pass.

The current scope also includes proved fixed-trip bit synthesis, natural-loop nesting/additive collapse, twelve-bit/two-parameter pure specialization, and bounded joint pass selection. Treat small timing regressions against a prior revision as measured tradeoffs, while semantic mismatches, invalid output and runtime-limit failures remain release blockers.

Checksum work adds a portfolio alternative that removes repeated positive-modulus reductions only after proving bounded unreduced arithmetic and exact restoration of externally used state, including zero-trip and trapping paths.
