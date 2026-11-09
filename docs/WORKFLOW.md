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

- **State** — Branch folding and unreachable-block removal now run before liveness. The public benchmark runner uses the organizer's kit from a separate checkout. Run `python3 tests/benchmark.py /path/to/LLH-26/Compilers/COMP10 --jobs 4`.
- **Latest evidence** — All 500 public sample comparisons agreed across five machines. Of those, 295 saved cycles, 202 tied, and three were slower by two to four cycles, all on `paren_depth`. Default-machine totals fell from 103,671 original cycles to 68,522, compared with 68,523 in the previous revision. The `unreachable_blocks` case improved from 8 original cycles to 4. Twelve CLI tests and 606 additional official validator comparisons passed. A generated 100,000-block case took under 0.6 seconds on the development Mac and produced identical output under two hash seeds.
- **Next change** — Investigate spill-aware fusion or register reuse using `paren_depth` and `spill_storm` traces. Use the public matrix to check the trade-off across machines.
- **Update before ending a session** — Record the latest verified command or benchmark, any open issue, and the next concrete step. Update [DESIGN.md](../DESIGN.md) for shipped passes and [Decisions](DECISIONS.md) for changed choices.
