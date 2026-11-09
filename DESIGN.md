# Oxygen Debt design

## What is implemented

The Python CLI parses KIR, validates the requested machine, and runs one block-local constant folding pass. With no folds, it emits the original bytes. The parser, machine loader, and fused-feature validation in `src/kirlib.py` are adapted from the official COMP10 starter kit at commit `d23ac1d`. [Upstream source](https://github.com/rudra-shroff06/LLH-26/blob/d23ac1d865df4cdacf7ad8e9fff3e1d560761c46/Compilers/COMP10/kirlib.py)

## Pass order

The CLI checks the input and machine before folding constants. The pass walks forward so later instructions can use facts learned from earlier definitions. The planned pass order after folding is recorded in the [technical plan](docs/TRD.md).

## Each pass

The folding pass tracks known register values from `const`, `mov`, and arithmetic in the current block. It replaces a known `add`, `sub`, or `mul` with the same destination and the precomputed value modulo 2³². It reads operand facts before updating the destination and drops the fact for any unmodeled write. It clears facts at each block entry because another path may reach the block with different values. The pass uses one forward scan and a source rewrite, taking expected linear time and linear space in the input size. [Research references](docs/RESEARCH.md)

## The machine

The CLI checks that the original program uses only supported fused operations. It replaces a known multiplication with a constant when `lat_alu` is at most `lat_mul`. The modeled latency comparison is local to the replacement.

## Keeping the behaviour

The replacements compute identical bits in the same destination. Loads, stores, volatile operations, branches, and potentially trapping arithmetic stay in the same order and retain their original operands. The official validator checks the ending, volatile log, and data memory. [Software requirements](docs/SRS.md)

## Profiles

The CLI accepts a profile path. The folding pass needs only the KIR and machine configuration.

## Known problems

Constants are tracked only inside a block. The first pass lowered cycle count on the wraparound regression case and produced equal cycle counts on the public sample suite. Copy elimination, dead-code removal, instruction scheduling, and register reuse remain planned. Folding can change which registers Kiln touches, so a valid replacement can still affect spill costs in either direction. [Verification and handoff](docs/WORKFLOW.md)
