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

- **State** — Profile-guided layout now runs after the other passes and uses the final block sizes. Run `python3 tests/benchmark.py /path/to/LLH-26/Compilers/COMP10 --jobs 4` using the external starter kit.
- **Latest evidence** — All 500 public sample comparisons and 110 comparisons with inverted profile counts matched original behavior. Compared with the previous revision, supplied profiles yielded 31 faster samples, 447 ties, and 22 slower samples. The default-machine total fell from 46,257 to 45,796, and the wide machine fell from 31,374 to 29,492. The few-register total rose from 122,264 to 122,341. Inverting the counts slowed 74 of 110 samples against the unprofiled layout. Eighteen CLI tests and 3,030 official validator comparisons passed. The profiled `collatz` output was identical under two hash seeds.
- **Next change** — Run release validation with additional generated inputs, confirm the submission requirements against the current repository, and prepare a reproducible demo.
- **Update before ending a session** — Record the latest verified command or benchmark, any open issue, and the next concrete step. Update [DESIGN.md](../DESIGN.md) for shipped passes and [Decisions](DECISIONS.md) for changed choices.
