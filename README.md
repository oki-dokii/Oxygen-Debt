# Oxygen Debt

Oxygen Debt is our entry for the COMP10 compiler challenge at the Low-Level Hackathon. The goal is to build `kopt`, a Python command that rewrites KIR programs to use fewer simulated Kiln cycles while preserving their behavior.

`kopt` folds constants across blocks when reachable paths agree, propagates copies, and reuses equivalent computations and memory reads within a block. It uses signed ranges to simplify division and prove when ordinary memory accesses are in bounds. It replaces isolated conditional copies and constants with `select`, simplifies known branches, and bypasses jump-only chains. It removes unreachable blocks, unused safe loads, and certain overwritten stores. It hoists invariant arithmetic and doubles short loops to reduce jumps. It also reuses register names to reduce spills and combines a multiply or shift with an addition when the machine supports the fused operation.

For simple counting loops, `kopt` can carry a proved memory value into the next iteration, preserving stores and traps.

Scheduling checks longer incoming/outgoing and repeated-cycle contexts when registers can spill, with deterministic limits that skip expensive candidates.

It also proves closed forms for bounded polynomial summations, schedules independent instructions, and specializes pure functions with at most twelve relevant masked input bits across up to two parameters. Specialization evaluates every value in the proven domain during compilation; it never reads benchmark input files or uses stored answers. [Proofs and limits](DESIGN.md)

Fixed-trip bit loops are proved with word expressions or GF(2) coefficients, enabling parallel population count, bit reflection and source-derived CRC maps. A bounded portfolio also tries nested-loop hoisting/additive collapse, different memory, unrolling, scheduling and allocation combinations, and a proved checksum-remainder deferral alternative. Profiles weight timing cases; they never justify a rewrite. A static-control candidate expands bounded, fully known loop paths without reading RAM and optionally keeps a bounded cache of successful literal-address loads through fresh value names. Affine branch diamonds can become a select plus arithmetic. Guarded loops can clamp their trip count and restore the original predicate before a late trap; proved address loops also offer pointer induction and four-way unrolling with a check after every body. A second timing round compares these candidates against the prior winner using additional zero/dense/alternating RAM cases. Counted groups of 2/4/8 bodies are offered for memory loops only when ranges guarantee a complete first group and no signed wrap; the original scalar loop handles the tail. Their final selection rejects any candidate slower on a timing case. `--no-search` disables the whole-function portfolio for pass diagnostics.

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

Replay the demo with the same external kit. It shows `sum_sq` on machines with and without fusion, finite specialization on `collatz`, static-control expansion and load reuse on `matmul4`, `matrix_add4` and `transpose8`, memory reuse on `stencil3`, bit synthesis on population count/reversal/CRC, nested-loop collapse, deferred checksum reductions, guarded-loop and branch conversion on `bounds_trap`/`branchy_select`, checked unrolling on `sieve`, and memory written before a division-by-zero trap.

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
python3 tests/rolling.py /path/to/LLH-26/Compilers/COMP10
python3 tests/advanced.py /path/to/LLH-26/Compilers/COMP10
python3 tests/metamorphic.py /path/to/LLH-26/Compilers/COMP10
python3 tests/modulo.py /path/to/LLH-26/Compilers/COMP10
python3 tests/expansion.py /path/to/LLH-26/Compilers/COMP10
python3 tests/control.py /path/to/LLH-26/Compilers/COMP10
python3 tests/groups.py /path/to/LLH-26/Compilers/COMP10
python3 tests/holdout.py /path/to/LLH-26/Compilers/COMP10
```

The 2026-11-13 local release run used organizer kit commit `d23ac1d` and all 100 supplied programs on five supplied machines. All 500 sample executions and 32,000 generated comparisons matched the independent organizer interpreter. These are summed sample cycles, not an official judging score or a prediction for unseen programs.

| Machine | Original cycles | Optimized cycles |
|---|---:|---:|
| Default | 103,671 | 12,911 |
| Few registers | 202,164 | 21,395 |
| No fused instructions | 107,966 | 14,637 |
| Slow memory | 111,254 | 21,125 |
| Wide/fast | 55,744 | 11,662 |

The default sample timings include `sum_sq` at 13 cycles, `collatz` at 18, and `spill_storm` at 19. These names appear only in validation and documentation, never in optimizer recognition. No supplied sample is slower than its unoptimized source. Against frozen release 439106e, 31 sample pairs improve and 469 tie, with no new public sample regressions (82,827 → 81,730 total cycles). Candidate timing still uses a fixed corpus and can favor a different version on another input. Default popcount and bit_reverse are 15 cycles each, nested_invariant is 11, crc_bitwise is 350, adler32 is 144, and fletcher16 is 96. Default matmul4 is 415 cycles, matrix_add4 is 120 and transpose8 is 354. Default sieve is 1,608 cycles, bounds_trap is 505 and branchy_select is 290. Default matvec8 is 65 cycles and row_sums is 48. The latest [memory hold-out](docs/FORWARDING.md) passes 5,520 comparisons on six unseen machines: 709 faster, 4,783 ties and 28 slower. Larger signed sorts use 7.02% fewer total cycles, with disclosed individual regressions. The preceding [backend qualification](docs/BACKEND.md) remains available separately. The earlier [counted-group qualification](docs/HOLDOUT.md) is retained separately.

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

The [global backend](docs/BACKEND.md) adds complete interference colouring, reaching-definition web splitting and pressure-aware scheduling as candidates against the preceding winner. Independent direct testing includes unselected forms, initial-zero values, dead writes, joins, loops and trap/volatile effects.

The [cross-block memory candidate](docs/FORWARDING.md) proves available values across every incoming edge, materializes conditional suppliers in fresh registers and optionally separates the first loop iteration before re-proving later loads. Initial guarded reads, all stores and volatile operations are preserved.
