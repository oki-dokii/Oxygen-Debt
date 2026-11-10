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
- **Latest evidence** — Twenty-five CLI tests passed. All 500 public samples and 32,000 generated inputs matched across five machines. Loop hoisting improved 10 pairs over `a2d3e40` and tied 490. The default sample total fell from 27,047 to 26,471 cycles against 103,671 original cycles. On the default machine, `nested_invariant` went from 1,057 to 627 cycles and `loop_invariant` from 337 to 191.
- **Fresh programs** — Run `python3 tests/stress.py /path/to/LLH-26/Compilers/COMP10`. Seeds 60723 and 921730 passed 9,600 comparisons across four machines. A separate local loop matrix used 60 programs across eight machines and 64 inputs for 30,720 comparisons, including 11,520 address traps. It exercised zero iterations, reads before definition, values live after the loop, changing operands, volatile logs, shuffled blocks, and skewed profiles.
- **Earlier verification** — Ubuntu 22.04 x86-64 with Python 3.10.12 passed the build, demo, 500 public samples, 32,000 generated inputs, and 4,800 fresh-program comparisons after signed division simplification. [Ubuntu run](https://github.com/oki-dokii/Oxygen-Debt/actions/runs/42775920239)
- **Next performance target** — Extend range facts to compound guards and use them to prove which ordinary memory accesses can trap. Start with `bounds_trap`, `dead_load_trap`, and `dead_overwritten_stores`. Keep the observable memory and volatile log intact up to a trap.
- **Handoff** — Confirm the organizers have read access to the private repository, then submit the repository link through the event's submission channel.
- **Update before ending a session** — Record the latest verified command or benchmark, any open issue, and the next concrete step. Update [DESIGN.md](../DESIGN.md) for shipped passes and [Decisions](DECISIONS.md) for changed choices.
