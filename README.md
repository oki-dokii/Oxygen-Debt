# Oxygen Debt

Oxygen Debt is our entry for the COMP10 compiler challenge at the Low-Level Hackathon. The goal is to build `kopt`, a Python command that rewrites KIR programs to use fewer simulated Kiln cycles while preserving their behavior.

`kopt` folds constants, propagates copies, and reuses equivalent computations within a block. It simplifies known branches, bypasses jump-only chains, and removes unreachable blocks and unused computations that cannot trap. It can write a result directly to its final register and combine a multiply or shift with an addition when the machine supports the fused operation.

Use Python 3.10 or later. Set `machine.cfg` to the path of a Kiln machine file, such as `machines/machine_default.cfg` from the official kit.

```sh
./build.sh
./kopt input.kir --machine machine.cfg -o output.kir
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests
```

The CLI accepts `--profile profile.prof` for compatibility with the judge's invocation. The current passes use static facts from the program.

Run the public sample matrix with the organizer's COMP10 directory from a separate checkout. The runner compares behavior before reporting cycle counts. Use `--details` for per-program results or `--optimizer /path/to/kopt` to evaluate another revision.

```sh
python3 tests/benchmark.py /path/to/LLH-26/Compilers/COMP10 --jobs 4
```

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
