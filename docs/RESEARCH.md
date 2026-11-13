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

## Implemented strategies and reasoning

On 2026-11-12 we implemented symbolic polynomial recurrence recognition, complete finite-domain specialization, and dependency scheduling.

For sums over `i=0..n-1`, use `sum(1)=n`, `sum(i)=n(n-1)/2`, `sum(i²)=n(n-1)(2n-1)/6`, and `sum(i³)=[n(n-1)/2]²`. These identities can be checked by taking the difference at `n+1` and `n`, plus the zero base case. Bound analysis justifies intermediate signed divisions; multiplication by the inverse of three modulo 2³² handles an exact division after halving. The implementation derives coefficients from the body rather than recognizing sample syntax. Additional proof conditions for signed remainder are recorded in [DESIGN](../DESIGN.md).

Finite specialization is partial evaluation after a dependency proof: masked original inputs partition all 32-bit words into at most 1,024 equivalence classes. Evaluate every class from source and verify every emitted candidate. The proof establishes coverage; randomized tests independently exercise the implementation. The permitted execution and timing code is copied from the pinned [organizer kirlib.py](https://github.com/rudra-shroff06/LLH-26/blob/d23ac1d865df4cdacf7ad8e9fff3e1d560761c46/Compilers/COMP10/kirlib.py), credited in `src/kiln.py`. The validator remains the unmodified external kit.

Scheduling preserves mutable-register dependencies and serializes potentially trapping operations with memory effects. Critical-path prioritization supplies a candidate; structural timing paths decide profitability. The short-path model missed spilling regressions, so the first version excluded those programs. A later version added bounded incoming/outgoing paths and repeated cycles before admitting spilling candidates, with a deterministic cost budget. Longer histories remain a limitation. [Decision log](DECISIONS.md)

## Rolling memory implementation — 2026-11-12

Implemented source-derived affine load/store forwarding across a single counting loop. The invariant is that a carry holds the next target address's last established memory value. Initial bounds and alias checks cover the base case and induction step. Safe transformation and profitability remain separate: original stores/traps stay in place, while structural timing paths and machine-capacity checks decide whether to emit a candidate. The first performance experiment exposed an interaction with loop doubling; preserving those existing plans removed the public regressions. See [DESIGN](../DESIGN.md) and D-026. The five-machine total is now 108,965 cycles (default 16,565), with 11 improved public pairs and no regressions against the preceding revision.

## Bit proofs and nested algebra — 2026-11-12

Word-parallel population count sums disjoint bit fields before gathering byte counts. Bit reflection is a sequence of width-1/2/4/8/16 swaps. Other fixed-trip pure bit loops are evaluated over affine GF(2) coefficient vectors: XOR, constant masks/shifts and restricted constant-difference conditionals preserve the representation. No sampled input is used to infer linearity. Additive-loop collapse instead proves a word-linear recurrence and sums the induction term with n(n−1)/2 under the bounded range proof. Both approaches derive rewrites from source semantics.

## Deferred checksum remainders — 2026-11-12

Implemented an independent congruence proof for bounded nonnegative checksum recurrences. Repeated reductions can move to the normal exit because addition and multiplication preserve congruence over the integers; the proof separately establishes that affected KIR operations never cross the signed boundary or wrap. A distinct mathematical bounds evaluator avoids mistaking a positive wrapped constant for a no-wrap proof. Restored outputs must be canonical for all possible exits, including the first exit before a value becomes tainted. Ordinary loads retain their original addresses/order, and body writes/I/O reject. See D-031 and DESIGN for resource bounds. The generated proof suite checks the pass and unselected compiler candidate directly, so selector fallback cannot hide an invalid rewrite.

## Static-control array loops — 2026-11-12

The implementation derives an execution path from exact abstract word constants and treats parameters and all memory/volatile results as unknown. A path is valid for every input only when every branch decision is exact; effect/trap order then follows by induction over the emitted trace. Fresh definitions allow a saved literal-address read to survive mutable source-register overwrites. Prior successful reads establish validity, and intervening stores invalidate possibly aliased entries. This derivation uses ordinary partial evaluation and value forwarding; it does not use sample memory. Direct generated fixtures include rectangular nests, aliasing outputs, scratch boundaries and effects.

## Data-dependent control targets — 2026-11-12

Affine arms of the form x+a / x+b can merge as x+select(cond,a,b) in the 32-bit ring. Reads before definition within either arm must count as escaping state, otherwise a carried temporary can be silently dropped. For an increasing unit-stride loop with an upper trap at L, min(n,L) gives exactly the completed work iterations; a late n>L decision reaches the original trap after the same effects. The original head predicate must be restored if the trap block reads it. Pointer translation preserves signed ordering only with explicit initial/bound/overshoot ranges. Four checked copies preserve the original test between every body, avoiding a divisibility or minimum-trip assumption.

Timing-case inspection exposed correlated zero arguments/zero RAM, which never entered flag-dependent marking loops. A separate control comparison now uses additional all-zero, all-one and alternating RAM patterns while retaining the prior portfolio winner. These observations influence candidate profitability, never validity. No program names or fixed array contents enter the compiler.

## Counted groups and hold-out qualification — 2026-11-13

For i'=i+s with s>0, i<n−(U−1)s proves that U original comparisons succeed. Bound the final overshoot as well, so a subsequent group cannot enter with a wrapped negative counter. Reproduce the original predicate as one before each copied body, and leave the original scalar loop to establish the final false predicate and remainder. A statically guaranteed first group avoids speculation on short entries. Development seed 932617 exposed short-loop setup penalties; production now combines that minimum-range proof with a per-case timing gate. Fresh seed 451729, not used to tune the compiler, exercises larger rectangular/overlapping matrices and unseen machines. Mathematical matrix oracles supplement the independent kit VM. Full evidence and reproduction commands are in HOLDOUT.md.

## Global register reuse follow-up

The implementation derives standard def-use webs from a reaching-definition fixed point, then uses backwards liveness to construct a mutable-register interference graph. Initial values and dead writes require explicit interference treatment in KIR. Colouring and version-based pressure estimates propose candidates; source-level proofs establish validity. [BACKEND.md](BACKEND.md) contains the implementation proof and test evidence.

## Cross-block memory follow-up

The memory candidate is derived from must-available equations and ordinary affine substitution modulo 2^32. Its odd-coefficient inverse is exact because an odd word is invertible modulo 2^32; even coefficients drop dependent facts. Common holders and CFG duplication do not themselves remove reads: a second complete analysis must prove availability at each replacement. The first iteration retains the original guarded read. No sample RAM or named sorting recipe is used. [Proof, bounds and reproducible qualification](FORWARDING.md).
