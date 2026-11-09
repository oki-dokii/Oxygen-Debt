# Research references

The reference snapshot is [LLH-26 commit d23ac1d](https://github.com/rudra-shroff06/LLH-26/tree/d23ac1d865df4cdacf7ad8e9fff3e1d560761c46/Compilers/COMP10). Start with the [KIR specification](https://github.com/rudra-shroff06/LLH-26/blob/main/Compilers/COMP10/KIR_SPEC.md), [benchmark index](https://github.com/rudra-shroff06/LLH-26/blob/main/Compilers/COMP10/bench/INDEX.md), and [worked examples](https://github.com/rudra-shroff06/LLH-26/blob/main/Compilers/COMP10/examples/EXAMPLES.md).

| Reference | Application to Oxygen Debt |
|---|---|
| [Briggs, Cooper, and Simpson, Value Numbering](https://bernsteinbear.com/assets/img/briggs-gvn.pdf) | Start with Figure 1 for repeated expressions within a block. Check that a register still holds the old value before reusing it. |
| [CompCert liveness analysis](https://compcert.org/doc/html/compcert.backend.Liveness.html) | Study backward dataflow and merging successor requirements. Apply KIR's own rules for which operations can be erased. |
| [Wegman and Zadeck, Constant Propagation with Conditional Branches](https://doi.org/10.1145/318593.318659) | Use reachable edges to improve constants at joins when we extend analysis beyond one block. |
| [Poletto and Sarkar, Linear Scan Register Allocation](https://doi.org/10.1145/330249.330250) | Use the lifetime idea to guide register name reuse. Kiln uses its own spill and issue rules, so compare actual simulated timing. |
| [Pettis and Hansen, Profile Guided Code Positioning](https://doi.org/10.1145/93542.93550) | Use edge weights to place likely successors next to their predecessors if we add layout. Check code placement costs as well as jump costs. |

The official benchmark index lists cleanup for 69 of the 100 practice programs, copy removal for 66, and scheduling for 70. The categories overlap. Cleanup and copy propagation give us a starting point, then we can use simulator traces to decide where scheduling is worth the effort.

These checks used the organizers' original and optimized files with the same sample input. They are reference measurements, not results from our optimizer.

| Example | Machine | Original cycles | Optimized cycles | What to investigate |
|---|---|---:|---:|---|
| `const_chain` | Default | 39 | 1 | Constant folding and algebraic cancellation |
| `sum_sq` | Default | 2,690 | 207 | Cleanup, fusion, and register reuse |
| `spill_storm` | Few registers | 6,767 | 2,874 | Sensitivity to register pressure |
| `dead_div_trap` | Default | 15 | 14 | Preserve division when a zero divisor can still trap |

The `sum_sq` example uses `mac`, so its optimized file is invalid on the no-fused machine. That is a useful machine-compatibility regression case.
