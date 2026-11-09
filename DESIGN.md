# Oxygen Debt design

## What is implemented

The Python CLI parses KIR, validates the requested machine, and runs local simplification, common subexpression elimination, branch folding, unreachable-block removal, dead-code removal, and instruction fusion. With no edits, it emits the original bytes. The parser, machine loader, and fused-feature validation in `src/kirlib.py` are adapted from the official COMP10 starter kit at commit `d23ac1d`. [Upstream source](https://github.com/rudra-shroff06/LLH-26/blob/d23ac1d865df4cdacf7ad8e9fff3e1d560761c46/Compilers/COMP10/kirlib.py)

## Pass order

The CLI checks the input and machine, walks forward to simplify expressions and branches within each block, and removes unreachable blocks. It then runs backward liveness on the remaining edges, which lets it discard definitions used only on removed paths. Fusion runs on retained instructions after liveness converges. [Technical plan](docs/TRD.md)

## Each pass

**Local simplification.** Track the value a register holds and which other registers still hold that value. Resolve sources before updating the destination, then remove that register from its former value's holders on overwrite. Start fresh at each block entry. Use KIR's 32-bit wraparound, signed comparison, and masked shifts when folding. The forward scan and output edits take expected linear time and space in the input size.

**Common subexpression elimination.** Key pure arithmetic, comparisons, and selects by their opcode and operand values. Normalize operand order for commutative operations. Reuse an expression only while a register still holds its result. Table lookups take expected constant time per instruction.

**Control flow.** Replace a branch with a jump if its condition is known within the block or both targets are identical. Follow the resulting edges from the entry label and delete unvisited labels and instructions. The traversal is iterative and takes linear time in the number of blocks and edges, plus the time to mark removed instructions.

**Dead-code removal.** Compute each block's live-out set from the union of its successors' live-in sets, then scan backward. Drop a pure instruction only if its destination is dead. Revisit predecessors when live-in changes. The cost grows with the total size of blocks and live sets visited. The worklist has a fixed budget of two million work units based on instruction visits, predecessor edges, and live-set entries. If the budget runs out, use dead-code removal only in blocks with no successors, where live-out is known to be empty.

**Instruction fusion.** Scan retained instructions backward with the current live set. Fuse an adjacent `mul` or constant-count `shl` into `add` only when the add reads the temporary once and its old value is dead after the add. The fused instruction reads the producer's original operands before writing the destination, including when the producer reads its own destination. The scan takes expected linear time plus the cost of forming live-out sets. [Research references](docs/RESEARCH.md)

## The machine

The CLI checks that the original program uses only supported fused operations. It simplifies a multiplication to a constant or copy when `lat_alu` is at most `lat_mul`. When spills can cost cycles, copy propagation keeps original register operands that are read in multiple blocks. Reuse of cheap expressions stays within uninterrupted spans of pure instructions under the same conditions. Fusion requires machine support and compares the fused latency with the sum of the two original latencies. [Decision log](docs/DECISIONS.md)

## Keeping the behaviour

The replacements compute identical bits in the same destination or use a register that holds the same value. A folded branch jumps to the target the original would take. Loads, stores, volatile operations, and trapping instructions in reachable blocks keep their order and original operands. The official validator checks the ending, volatile log, and data memory. [Software requirements](docs/SRS.md)

## Profiles

The CLI accepts a profile path. The current optimizer passes need only the KIR and machine configuration. The benchmark runner forwards sample profiles when supplied by the organizer.

## Known problems

Value tracking stops at block boundaries, so branch folding uses conditions known within a block. Fusion uses local latency and may expose register reload stalls. The public `paren_depth` sample takes two to four additional cycles on three machines after fusion. Scheduling and register reuse remain planned. [Verification and handoff](docs/WORKFLOW.md)
