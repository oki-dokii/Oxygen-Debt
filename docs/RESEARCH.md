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

## Implemented strategies and reasoning

On 2026-11-12 we implemented three general strategies independently: symbolic polynomial recurrence recognition, complete finite-domain specialization, and dependency scheduling. The local default total at the comparison revision was 16,645 cycles; that remains above the other implementation's unverified reported 8,700. Do not present this as a head-to-head result or a winning guarantee.

For sums over `i=0..n-1`, use `sum(1)=n`, `sum(i)=n(n-1)/2`, `sum(i²)=n(n-1)(2n-1)/6`, and `sum(i³)=[n(n-1)/2]²`. These identities can be checked by taking the difference at `n+1` and `n`, plus the zero base case. Bound analysis justifies intermediate signed divisions; multiplication by the inverse of three modulo 2³² handles an exact division after halving. The implementation derives coefficients from the body rather than recognizing sample syntax. Additional proof conditions for signed remainder are recorded in [DESIGN](../DESIGN.md).

Finite specialization is partial evaluation after a dependency proof: masked original inputs partition all 32-bit words into at most 1,024 equivalence classes. Evaluate every class from source and verify every emitted candidate. The proof establishes coverage; randomized tests independently exercise the implementation. The permitted execution and timing code is copied from the pinned [organizer kirlib.py](https://github.com/rudra-shroff06/LLH-26/blob/d23ac1d865df4cdacf7ad8e9fff3e1d560761c46/Compilers/COMP10/kirlib.py), credited in `src/kiln.py`. The validator remains the unmodified external kit. No competitor implementation code was copied.

Scheduling preserves mutable-register dependencies and serializes potentially trapping operations with memory effects. Critical-path prioritization supplies a candidate; structural timing paths decide profitability. The short-path model missed spilling regressions, so the first version excluded those programs. A later version added bounded incoming/outgoing paths and repeated cycles before admitting spilling candidates, with a deterministic cost budget. Longer histories remain a limitation. [Decision log](DECISIONS.md)

## Updated public comparison — 2026-11-12

[Full comparison](COMPARISON.md) pins both peers, compares all 500 published C++ result rows with our verified `040642d` results, and records architectural and testing differences. Our five-machine total is 109,416 versus ROCA's reported 163,533 and the C++ entry's reported 52,130. Against the latter's published rows, we win 26 pairs, tie 39 and lose 435. These are comparisons with author-reported data, not independently reproduced competitor runs. The most substantial remaining gaps include global loop/memory work, bit-operation synthesis, allocation and a broader candidate portfolio.

## Rolling memory implementation — 2026-11-12

Implemented source-derived affine load/store forwarding across a single counting loop, independently of competitor code. The invariant is that a carry holds the next target address's last established memory value. Initial bounds and alias checks cover the base case and induction step. Safe transformation and profitability remain separate: original stores/traps stay in place, while structural timing paths and machine-capacity checks decide whether to emit a candidate. The first performance experiment exposed an interaction with loop doubling; preserving those existing plans removed the public regressions. See [DESIGN](../DESIGN.md) and D-026. The five-machine total is now 108,965 cycles (default 16,565), with 11 improved public pairs and no regressions against the comparison revision. The earlier [public comparison](COMPARISON.md) remains a pinned historical comparison, not a measurement of this new revision.

## Bit proofs, nested algebra and current comparison — 2026-11-12

Word-parallel population count sums disjoint bit fields before gathering byte counts. Bit reflection is a sequence of width-1/2/4/8/16 swaps. Other fixed-trip pure bit loops are evaluated over affine GF(2) coefficient vectors: XOR, constant masks/shifts and restricted constant-difference conditionals preserve the representation. No sampled input is used to infer linearity. Additive-loop collapse instead proves a word-linear recurrence and sums the induction term with n(n−1)/2 under the bounded range proof. Both approaches were implemented independently; references to peer designs describe scope, not copied code.

[The refreshed comparison](COMPARISON.md) pins ROCA at unchanged `1485b298` and the C++ peer at new `761489fe`. The peer now reports 51,122 summed sample cycles; its older per-case JSON belongs to an earlier stage and is not mixed with that new claim. Our corresponding local total is 99,024. New candidate/profile and metamorphic-test limits are recorded in DESIGN and WORKFLOW.

## Deferred checksum remainders — 2026-11-12

Implemented an independent congruence proof for bounded nonnegative checksum recurrences. Repeated reductions can move to the normal exit because addition and multiplication preserve congruence over the integers; the proof separately establishes that affected KIR operations never cross the signed boundary or wrap. A distinct mathematical bounds evaluator avoids mistaking a positive wrapped constant for a no-wrap proof. Restored outputs must be canonical for all possible exits, including the first exit before a value becomes tainted. Ordinary loads retain their original addresses/order, and body writes/I/O reject. See D-031 and DESIGN for resource bounds. The generated proof suite checks the pass and unselected compiler candidate directly, so selector fallback cannot hide an invalid rewrite.
