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

- **State** — Release validation and the replayable demo are ready. Run `sh tests/demo.sh /path/to/LLH-26/Compilers/COMP10`. The repository contains all four required top-level files, executable entry points with LF line endings, and no copies of the organizer's benchmark or machine folders.
- **Latest evidence** — Thirty-one CLI tests passed. All 500 public samples and 32,000 generated inputs matched across five machines. Loop doubling improved 176 pairs over `e2f11d5` and tied 324. The default sample total fell from 25,915 to 24,157 cycles against 103,671 original cycles. On the default machine, `sieve` went from 2,016 to 1,764 cycles and `matmul4` from 1,018 to 826.
- **Fresh programs** — Run `python3 tests/stress.py /path/to/LLH-26/Compilers/COMP10`. Seeds 60723 and 921730 passed 9,600 comparisons across four machines. A local loop matrix used 48 programs across eight machines and 64 inputs for 24,576 comparisons, including 6,848 address traps. The pass doubled loops on 216 program and machine pairs. Cases covered zero, odd, and even iteration counts, extra entries, volatile bodies, and traps in either body copy.
- **Earlier verification** — Ubuntu 22.04 x86-64 with Python 3.10.12 passed the build, demo, 500 public samples, 32,000 generated inputs, and 4,800 fresh-program comparisons after branch inversion. [Ubuntu run](https://github.com/oki-dokii/Oxygen-Debt/actions/runs/42779223672)
- **Next performance target** — Test a second jump-threading pass after dead-code removal. Compare the cost of bypassing blocks that have become jump-only with retaining their existing fallthroughs.
- **Handoff** — Confirm the organizers have read access to the private repository, then submit the repository link through the event's submission channel.
- **Update before ending a session** — Record the latest verified command or benchmark, any open issue, and the next concrete step. Update [DESIGN.md](../DESIGN.md) for shipped passes and [Decisions](DECISIONS.md) for changed choices.
