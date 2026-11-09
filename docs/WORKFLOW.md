# Development workflow and handoff

Start each session here. Read the [current requirements](SRS.md), [technical plan](TRD.md), and [decision log](DECISIONS.md) before changing the optimizer. Check the Git diff and use the current implementation and tests to verify this handoff.

| Stage | Work | Check before proceeding |
|---|---|---|
| 1. Baseline command | Add `build.sh`, the Python `kopt` entry point, and the permitted kit code it uses. Read the machine and emit the input unchanged. | The documented command works from a clean checkout and from another directory. |
| 2. First passes | Implement local constant folding and copy propagation, then add liveness and dead pure code removal. | Verify a beneficial rewrite and a case where each pass must preserve the original behavior. |
| 3. Batch validation | Compare originals with optimized outputs under the official validator, then measure cycles with the simulator. | Check public workloads across supplied machines, repeated-run determinism, and runtime on a generated large program. |
| 4. Performance work | Add fusion, register reuse, or scheduling in separate changes. | Keep changes with measured benefits. Investigate slower cases and retain a reproducer for failures. |
| 5. Submission | Update the root README and the seven required design sections. Build from a clean checkout and record demo and benchmark evidence. | Review the submission checklist and confirm organizer access before sending the repository link. |

For each change, write down the fact that makes the rewrite safe. Add a small test when the public suite would miss the failure mode. Start with `const_chain`, `junk_dead`, and `common_subexpr` for wins, then run `dead_div_trap`, `sensor_sum`, and `alias_hazard` as guardrails. Include same-input cycle comparisons and record skipped validator inputs separately from passing inputs.

## Current handoff

- **State** — Common subexpression elimination and machine-dependent fusion are implemented. The public benchmark runner uses the organizer's kit from a separate checkout. Run `python3 tests/benchmark.py /path/to/LLH-26/Compilers/COMP10 --jobs 4`.
- **Latest evidence** — All 500 public sample comparisons agreed across five machines. Of those, 295 saved cycles, 202 tied, and three were slower by two to four cycles, all on `paren_depth`. On the default machine, total sample cycles fell from 103,671 to 68,523. The previous optimizer measured 76,288 with the same runner. Ten CLI tests and 2,020 additional official validator comparisons pass. The 100,000-instruction check took about 0.6 seconds on the development Mac and produced identical output under two hash seeds.
- **Next change** — Fold branches whose conditions are known, then remove unreachable blocks. Use the benchmark runner to evaluate the impact and preserve labels on all reachable paths. Follow up with spill-aware fusion or register reuse based on the traces.
- **Update before ending a session** — Record the latest verified command or benchmark, any open issue, and the next concrete step. Update [DESIGN.md](../DESIGN.md) for shipped passes and [Decisions](DECISIONS.md) for changed choices.
