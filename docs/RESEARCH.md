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

## Other public implementations

Checked on 2026-11-11 using GitHub repository and code search, then read the public documentation. The following are separate implementations of this exact COMP10 challenge. Their performance numbers are author-reported and have not been reproduced with our runner.

| Repository | Documented approach | Reported result |
|---|---|---|
| [RohitKattimani/COMP10_ROKACODE](https://github.com/RohitKattimani/COMP10_ROKACODE/tree/1485b298f36e8027cd7c332949933af5b6001c7a) | Python, local optimization, loop recognition, graph coloring, and a bounded square-sum formula | `sum_sq` on the default machine at 21 cycles. Its report gives 163,533 optimized cycles summed across five machines. |
| [wildwolf07/kopt-kiln-optimizer](https://github.com/wildwolf07/kopt-kiln-optimizer/tree/1689c93ce8ae4629914aef090bf2a097e31b66c9) | C++17, SSA, machine-aware candidate search, scheduling, and structural specialization | The README's candidate table gives 8,700 cycles summed across default-machine samples. It allows individual timing regressions. |

The second repository's default-machine original total is 103,671, matching the original total in our runner. That makes its reported result worth independently investigating, while a performance comparison still needs the same pinned kit, inputs, executable revision, and runner. Closed forms and scheduling are the clearest documented areas to examine next. Implementation work in this session remained independently developed.
