# Decision log

Record a new entry when a decision changes architecture, behavior, validation, or scope. Link the commit or evidence once it exists.

| ID | Status | Decision and rationale | Revisit when |
|---|---|---|---|
| D-001 | Accepted | Use Python 3.10+ and the permitted starter KIR parser and machine loader. Python is available on the judging system and gives us a short path to a working command. Credit reused kit code in the design record. | Profiling identifies an implementation bottleneck that survives simpler fixes. |
| D-002 | Accepted | Begin with KIR basic blocks and local value tracking. KIR permits register reassignment, and the first passes can work without introducing SSA or phi nodes. | An important cross-block optimization needs a representation the current model cannot support clearly. |
| D-003 | Accepted | Use static facts to justify rewrites and the official tools to catch regressions and measure performance. Keep correctness decisions independent of observed sample inputs and branch profiles. | A new pass needs stronger static facts such as ranges or alias information. |
| D-004 | Accepted | Prioritize local cleanup and safe dead-code removal. Add machine-specific passes only after we can measure each pass and identify regressions. | The first milestone passes the regression matrix. |
| D-005 | Accepted | Keep the starter workloads in a separate checkout. Commit original targeted tests, pass decisions, and reproducible benchmark instructions. | Organizers revise what can be submitted. |
| D-006 | Accepted | When the input names more registers than Kiln can hold, preserve copy operands read in multiple blocks. Unrestricted propagation extended temporary lifetimes and increased spill costs on several public samples. This policy recovered those cases at the cost of skipping some profitable copies. | A later pass can estimate register pressure with more precise live ranges. |
