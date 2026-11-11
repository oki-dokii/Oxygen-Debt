# Oxygen Debt

Oxygen Debt is our entry for the COMP10 compiler challenge at the Low-Level Hackathon. The goal is to build `kopt`, a Python command that rewrites KIR programs to use fewer simulated Kiln cycles while preserving their behavior.

`kopt` folds constants across blocks when reachable paths agree, propagates copies, and reuses equivalent computations and memory reads within a block. It uses signed ranges to simplify division and prove when ordinary memory accesses are in bounds. It replaces isolated conditional copies and constants with `select`, simplifies known branches, and bypasses jump-only chains. It removes unreachable blocks, unused safe loads, and certain overwritten stores. It hoists invariant arithmetic and doubles short loops to reduce jumps. It also reuses register names to reduce spills and combines a multiply or shift with an addition when the machine supports the fused operation.

It also proves closed forms for bounded polynomial summations, schedules independent instructions, and specializes pure functions with at most ten relevant masked input bits. Specialization evaluates every value in the proven domain during compilation; it never reads benchmark input files or uses stored answers. [Proofs and limits](DESIGN.md)

Use Python 3.10 or later. Set `machine.cfg` to the path of a Kiln machine file, such as `machines/machine_default.cfg` from the official kit.

```sh
./build.sh
./kopt input.kir --machine machine.cfg -o output.kir
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests
```

The optional `--profile profile.prof` supplies edge counts for block layout. The optimizer uses them to estimate timing while keeping the entry block first and preserving explicit branch targets.

Run the public sample matrix with the organizer's COMP10 directory from a separate checkout. The runner compares behavior before reporting cycle counts. Use `--details` for per-program results or `--optimizer /path/to/kopt` to evaluate another revision.

```sh
python3 tests/benchmark.py /path/to/LLH-26/Compilers/COMP10 --jobs 4
```

Replay the demo with the same external kit. It shows `sum_sq` on machines with and without fusion, finite specialization on `collatz`, scheduling on `matmul4`, and memory written before a division-by-zero trap.

```sh
sh tests/demo.sh /path/to/LLH-26/Compilers/COMP10
```

For the release validation run, add `--random 64 --seed 832719` to the benchmark command. Generated inputs are used for correctness checks. The reported cycle counts use the supplied sample inputs.

The stress suite generates fresh KIR with memory aliases, traps, volatile I/O, and bounded loops. It compares both executions with the organizer's interpreter on the default machine and three synthetic machines.

```sh
python3 tests/stress.py /path/to/LLH-26/Compilers/COMP10
python3 tests/summations.py /path/to/LLH-26/Compilers/COMP10
python3 tests/finite.py /path/to/LLH-26/Compilers/COMP10
python3 tests/scheduling.py /path/to/LLH-26/Compilers/COMP10
```

The 2026-11-12 local release run used organizer kit commit `d23ac1d` and all 100 supplied programs on five supplied machines. All 500 sample executions and 32,000 generated comparisons matched the independent organizer interpreter. These are summed sample cycles, not the judges' geometric-mean score or a prediction for unseen programs.

| Machine | Original cycles | Optimized cycles |
|---|---:|---:|
| Default | 103,671 | 16,690 |
| Few registers | 202,164 | 32,407 |
| No fused instructions | 107,966 | 19,115 |
| Slow memory | 111,254 | 25,752 |
| Wide/fast | 55,744 | 16,808 |

The default sample timings include `sum_sq` at 13 cycles, `collatz` at 18, and `spill_storm` at 19. These names appear only in validation and documentation, never in optimizer recognition. No supplied sample slowed against either the unoptimized source or the revision before these three passes.

The parser and machine loader in `src/kirlib.py`, and execution and timing code in `src/kiln.py`, reuse permitted organizer code from the [pinned kit](https://github.com/rudra-shroff06/LLH-26/blob/d23ac1d865df4cdacf7ad8e9fff3e1d560761c46/Compilers/COMP10/kirlib.py). The optimizer passes and generated test suites are our implementation. Runtime requires only the Python standard library; the external kit is used for independent validation.

The [workflow and handoff](docs/WORKFLOW.md) records the latest measured results and next step.

| Document | Use it for |
|---|---|
| [PRD](docs/PRD.md) | Project goal, scope, and success criteria |
| [TRD](docs/TRD.md) | Optimizer architecture and pass design |
| [SRS](docs/SRS.md) | Verifiable requirements and judging constraints |
| [Decisions](docs/DECISIONS.md) | Choices we made and when to revisit them |
| [Research](docs/RESEARCH.md) | Official materials, compiler papers, and starter-kit measurements |
| [DESIGN.md](DESIGN.md) | The implementation record in the organizers' required format |

[Official COMP10 starter kit](https://github.com/rudra-shroff06/LLH-26/tree/main/Compilers/COMP10)
