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
- **Latest evidence** — Nineteen CLI tests passed. All 500 public samples and 32,000 generated inputs matched across five machines. Load reuse cut the default sample total from 45,796 to 45,427 cycles against 103,671 original cycles. It improved 11 public program and machine pairs over revision `2929d83` and tied the other 489. The default run of `redundant_loads` went from 527 to 163 cycles.
- **Fresh programs** — Run `python3 tests/stress.py /path/to/LLH-26/Compilers/COMP10`. The suite checks 100 generated programs on four machines with 12 inputs each, for 4,800 comparisons. It covers aliasing, address bounds, volatile I/O, bounded loops, shuffled block order, and misleading profiles. Retiming these executions against `2929d83` found 942 faster and 3,858 tied after applying the spill guard. A separate local stress case with 100,068 memory-heavy instructions produced identical output under two Python hash seeds and matched the organizer's interpreter on five inputs.
- **Earlier verification** — The manual GitHub Actions workflow passed on Ubuntu 22.04 x86-64 with Python 3.10.12 before load reuse. It ran the build, 18 CLI tests, the demo, 500 public samples, and 32,000 generated comparisons. A separate local run of renamed registers and shuffled non-entry blocks matched on all 500 transformed samples and 4,000 extra generated inputs. [Ubuntu run](https://github.com/oki-dokii/Oxygen-Debt/actions/runs/42592154861)
- **Next performance target** — Measure register reuse on `matmul4`, `bubble_sort`, and `spill_storm`. Retiming the same optimized traces with the default machine's spill penalty set to zero cut those traces from 3,273 to 1,018, 2,986 to 989, and 1,860 to 283 cycles respectively. Those numbers isolate how much time spills account for on these traces.
- **Handoff** — Confirm the organizers have read access to the private repository, then submit the repository link through the event's submission channel.
- **Update before ending a session** — Record the latest verified command or benchmark, any open issue, and the next concrete step. Update [DESIGN.md](../DESIGN.md) for shipped passes and [Decisions](DECISIONS.md) for changed choices.
