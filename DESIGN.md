# Oxygen Debt design

## What is implemented

The Python CLI parses KIR, validates the requested machine, and runs local simplification and dead-code removal. With no edits, it emits the original bytes. The parser, machine loader, and fused-feature validation in `src/kirlib.py` are adapted from the official COMP10 starter kit at commit `d23ac1d`. [Upstream source](https://github.com/rudra-shroff06/LLH-26/blob/d23ac1d865df4cdacf7ad8e9fff3e1d560761c46/Compilers/COMP10/kirlib.py)

## Pass order

The CLI checks the input and machine, walks forward to simplify each block, then runs backward liveness over the resulting control flow. Doing simplification first lets liveness remove definitions whose uses were replaced with constants or copies. [Technical plan](docs/TRD.md)

## Each pass

**Local simplification.** Track the value a register holds and which other registers still hold that value. Resolve sources before updating the destination, then remove that register from its former value's holders on overwrite. Start fresh at each block entry. Use KIR's 32-bit wraparound, signed comparison, and masked shifts when folding. The forward scan and output edits take expected linear time and space in the input size.

**Dead-code removal.** Compute each block's live-out set from the union of its successors' live-in sets, then scan backward. Drop a pure instruction only if its destination is dead. Revisit predecessors when live-in changes. The cost grows with the total size of blocks and live sets visited. The worklist has a fixed budget of two million work units based on instruction visits, predecessor edges, and live-set entries. If the budget runs out, use dead-code removal only in blocks with no successors, where live-out is known to be empty. [Research references](docs/RESEARCH.md)

## The machine

The CLI checks that the original program uses only supported fused operations. It simplifies a multiplication to a constant or copy when `lat_alu` is at most `lat_mul`. If the input has more register names than the machine's capacity, copy propagation keeps original register operands that are read in multiple blocks. This avoids extending some temporary lifetimes when the copy may still be needed on an outgoing edge. [Decision log](docs/DECISIONS.md)

## Keeping the behaviour

The replacements compute identical bits in the same destination or use a register that holds the same value. Propagating into a branch changes only how it obtains the same condition. Loads, stores, volatile operations, and trapping instructions keep their order and original operands. The official validator checks the ending, volatile log, and data memory. [Software requirements](docs/SRS.md)

## Profiles

The CLI accepts a profile path. The folding pass needs only the KIR and machine configuration.

## Known problems

Value tracking stops at block boundaries. The optimizer leaves reachability, common subexpression elimination, scheduling, and register reuse for later passes. Changes to register reads may still affect spill costs on unseen workloads. [Verification and handoff](docs/WORKFLOW.md)
