# Technical requirements and design

Use Python 3.10+ and the permitted starter parser and machine loader from `kirlib.py`. Parse into ordered basic blocks with typed operands. Track the entry block explicitly. Derive successors from each terminator and compute predecessors when a pass needs them. Reuse the kit's operand representation where practical and write a small deterministic KIR emitter.

```mermaid
flowchart LR
    A["KIR and machine configuration"] --> B["Parse KIR into ordered blocks"]
    B --> C["Simplify arithmetic and propagate copies"]
    C --> D["Simplify branches and remove unreachable blocks"]
    D --> E["Compute liveness and remove dead pure instructions"]
    E --> F["Apply measured machine-specific passes"]
    P["Optional edge counts"] --> F
    F --> G["Emit valid KIR"]
    G --> H["Offline validation and cycle measurement"]
```

| Pass | Initial approach | Safety condition |
|---|---|---|
| Constants and copies | Seed each block with exact facts from range analysis. Walk forward within each block to track literals and current value identities. | Keep an entry constant only when the reachable incoming paths agree. Read all source facts before changing the destination and resolve copies only while their values are held. |
| Redundant arithmetic | Key pure expressions by opcode and the current operand values. Canonicalize operand order only for commutative operations. | Reuse an earlier result only while it remains available in a register. Begin with arithmetic and comparisons. |
| Load reuse | Track reads and writes by address value within a block. Discard facts a store could overwrite. | An earlier access to the same address must have succeeded on every path that reaches the replacement. The recorded value must still be available. |
| Memory cleanup | Use signed ranges to prove addresses are in bounds. Drop unused loads and match overwritten stores within trap-free continuations. | Require addresses in 0 through 4095. Stop store matching at reads or volatile operations and preserve the store sequence on any trapping path. |
| Signed division and remainder | Propagate signed intervals through blocks and direct comparison edges. Reduce an exact divisor to cheaper arithmetic or an inline literal. | Prove the divisor is nonzero. Preserve signed rounding, the sign of the remainder, and 32-bit overflow. |
| Branches and reachability | Fold known conditions, invert comparisons with zero, and traverse the remaining edges from the entry block. | Inversion swaps both targets and requires a register that still holds the tested value. Remove blocks only when unreachable. |
| Conditional assignments | Replace a pair of copy or constant assignments with a select before their common successor. | The arms must have one incoming edge each, assign the same register, and contain no other operations. |
| Late jump cleanup | Bypass newly jump-only blocks after layout and return directly from jumps to return-only blocks. | Keep jump cycles and protect shared fallthrough chains. Retain the original return operand and all effects on the path. |
| Block merging | Remove a redundant jump and label from adjacent blocks after allocation and layout. | The target must have a single incoming edge and be adjacent in both source and output order. Preserve the instruction sequence and register names. |
| Loop hoisting | Move groups of invariant arithmetic from a simple loop body into its existing entry block. Limit the group to one result read by the remaining body. | The operations must be pure, their operands invariant, and their destinations defined once in the loop and read only later in the body. |
| Loop doubling | Let alternating copies of a short loop body share a taken back edge. Check machine register and cache capacity after layout. | Keep the first check and a check after each body copy. Require a sole-entry body and skip volatile operations. |
| Liveness and dead code | Compute live-out as the union of successor live-ins. Use a backward worklist and scan instructions in reverse to find dead definitions. | Delete only pure, non-trapping instructions whose destination is dead. Keep stores, volatile operations, and potential traps. |
| Fusion | Recognize nearby multiply-add and shift-add patterns. Check machine features and compare modeled costs. | The intermediate value must be removable, operands must still denote the same values, and the fused shift count must be a legal literal. |
| Register reuse | Assign a shared pool of register names to block-local definitions after liveness and fusion. Use the machine's register count and estimate reloads on short cycles that could still spill. | Reserve parameters, registers live at block boundaries, and registers used by volatile I/O. Read operands before freeing their names for new definitions. |

Keep the local passes linear in the number of instructions where practical. Avoid tables indexed by the largest register number and full scans for each individual rewrite. Use stable iteration order and a deterministic work budget for optional expensive analyses. The original input is a fallback when it is valid for the selected machine. Handle unsupported fused opcodes deliberately if the input contract requires lowering them, and document the behavior before relying on that path.

The optimizer reads no benchmark inputs. The offline runner invokes the independent official tools on original and optimized programs with identical inputs and machine settings. Use trace output to investigate instruction issue stalls, branch penalties, and register spill regressions.
