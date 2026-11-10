# Oxygen Debt design

## What is implemented

The Python CLI parses KIR, validates the requested machine, and runs local simplification, common subexpression elimination, load reuse, branch folding, jump threading, unreachable-block removal, dead-code removal, copy elision, instruction fusion, and register reuse. A supplied profile can guide block layout. With no edits, the CLI emits the original bytes. The parser, machine loader, and fused-feature validation in `src/kirlib.py` are adapted from the official COMP10 starter kit at commit `d23ac1d`. [Upstream source](https://github.com/rudra-shroff06/LLH-26/blob/d23ac1d865df4cdacf7ad8e9fff3e1d560761c46/Compilers/COMP10/kirlib.py)

## Pass order

The CLI checks the input and machine, walks forward to simplify expressions and branches within each block, threads jumps, and removes unreachable blocks. It then runs backward liveness on the remaining edges, which lets it discard definitions used only on removed paths. Copy elision and fusion run on retained instructions after liveness converges. Register reuse then renames local values, and layout runs last using the final instruction counts. [Technical plan](docs/TRD.md)

## Each pass

**Local simplification.** Track the value a register holds and which other registers still hold that value. Resolve sources before updating the destination, then remove that register from its former value's holders on overwrite. Start fresh at each block entry. Use KIR's 32-bit wraparound, signed comparison, and masked shifts when folding. The forward scan and output edits take expected linear time and space in the input size.

**Common subexpression elimination.** Key pure arithmetic, comparisons, and selects by their opcode and operand values. Normalize operand order for commutative operations. Reuse an expression only while a register still holds its result. Table lookups take expected constant time per instruction.

**Load reuse.** Record the value read or written at each address within a block. A store to a literal address invalidates facts for all dynamic addresses and updates its own slot. A dynamic store invalidates both tables before recording its value. Reuse a literal or a register that still holds the recorded value. Reaching the second access proves that the earlier access to that address succeeded, so the removed load cannot introduce a new trap. The two tables take linear total work to maintain because each cleared entry must first have been inserted.

**Control flow.** Replace a branch with a jump if its condition is known within the block or both targets are identical. Resolve each chain of jump-only blocks to its endpoint, caching the result for every hop. Paths that enter a jump cycle keep their original edges. Redirect branches and jumps to resolved endpoints, then follow the resulting edges from the original entry and delete unvisited labels and instructions. The walks are iterative and take linear time in the number of blocks and edges, plus the time to mark removed instructions.

**Dead-code removal.** Compute each block's live-out set from the union of its successors' live-in sets, then scan backward. Drop a pure instruction only if its destination is dead. Revisit predecessors when live-in changes. The cost grows with the total size of blocks and live sets visited. The worklist has a fixed budget of two million work units based on instruction visits, predecessor edges, and live-set entries. If the budget runs out, use dead-code removal only in blocks with no successors, where live-out is known to be empty.

**Copy elision and instruction fusion.** Scan retained instructions backward with the current live set. A pure computation followed by a copy can write directly to the copy's destination if the temporary is dead after the copy. Fuse an adjacent `mul` or constant-count `shl` into `add` only when the add reads the temporary once and its old value is dead after the add. Multiplication by a power of two is equivalent to a left shift modulo 2³², so that pair can also use `addsh`. Both rewrites read the producer's original operands before writing the final destination, including when the producer reads that register. The scan takes expected linear time plus the cost of forming live-out sets. [Research references](docs/RESEARCH.md)

**Register reuse.** Reserve parameters, registers live at block boundaries, and every register used by volatile I/O. In each block, walk backward to locate the last read of each remaining definition, then assign those definitions names from a shared pool. A name becomes available after its last read, including before the same instruction writes its result. Each read therefore sees the same definition as before. Sorting the names and allocating with a heap take O((N + R) log R) time for N instructions and R register names.

**Block layout.** Sort surviving edges by profile weight and join chains at their tails and heads, keeping the entry first. Compare the proposed order with the current one using estimated taken-branch and instruction-cache penalties. Sorting costs O(E log E) for E candidate edges, and scoring scans the retained blocks and instructions. Moving labeled blocks preserves every explicit transfer. [Profile-guided code positioning](https://doi.org/10.1145/93542.93550)

## The machine

The CLI checks that the original program uses only supported fused operations. It simplifies a multiplication to a constant or copy when `lat_alu` is at most `lat_mul` and applies a similar check against `lat_load` for load reuse. When spilling can cost more than loading, it keeps literal-address and self-overwriting loads that would gain a register read. When spills can cost cycles, copy propagation keeps original register operands that are read in multiple blocks, copy elision removes intermediate writes, and reuse of cheap expressions stays within uninterrupted spans of pure instructions. Fusion requires machine support and compares the fused latency with the sum of the two original latencies. When both fused forms apply, it chooses `addsh` if it has lower latency. Register reuse runs when the remaining names exceed the machine's register count and spilling has a cost. If the new program would still spill, it estimates reloads on repeated one- and two-block cycles and restores the original names in those blocks when the estimate rises. [Decision log](docs/DECISIONS.md)

## Keeping the behaviour

The replacements compute identical bits in the same destination or use a register that holds the same value. A folded branch jumps to the target the original would take. Threading skips only unconditional jumps, which have no register, memory, or volatile effects. The pass keeps the order and operands of reachable stores, volatile operations, and operations that can still trap. Volatile accesses use a separate device state, so they preserve ordinary memory facts. The official interpreter checks the ending, volatile log, and data memory. [Software requirements](docs/SRS.md)

## Profiles

Only layout uses profile counts. It ignores malformed entries and counts for edges absent from the optimized graph. It gives existing fallthrough edges a small bias to retain them when counts are close or missing. Block visit estimates use the larger of incoming and outgoing observed counts. A missing or unreadable profile leaves layout in source order. An inaccurate profile can change the layout and cycle count while leaving execution behavior intact.

## Known problems

Value tracking stops at block boundaries, so branch folding uses conditions known within a block. Jump threading runs before liveness and can miss blocks made jump-only by dead-code removal. The layout estimate treats branch and cache penalties as additive and cannot account for overlap with register reloads or inaccurate counts. The register reuse guard uses reload counts from one- and two-block cycles as a proxy for timing. [Verification and handoff](docs/WORKFLOW.md)
