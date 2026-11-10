"""Remove overwritten stores on paths whose continuations cannot trap."""


def remove_overwritten_stores(blocks, edits, safe_memory):
    predecessors = {label: [] for label in blocks}
    may_trap = set()
    for label, block in blocks.items():
        for kind, target in block[-1].args:
            if kind == "l":
                predecessors[target].append(label)
        if any(instruction.op in {"div", "mod", "trap"}
               or (instruction.op in {"load", "store"} and instruction.line not in safe_memory)
               for instruction in block):
            may_trap.add(label)

    pending = list(may_trap)
    while pending:
        for predecessor in predecessors[pending.pop()]:
            if predecessor not in may_trap:
                may_trap.add(predecessor)
                pending.append(predecessor)

    for label, block in blocks.items():
        if label in may_trap:
            continue
        previous_stores = {}
        removed = set()
        for instruction in block:
            if instruction.op == "store":
                key = safe_memory[instruction.line]
                previous = previous_stores.get(key)
                if previous is not None:
                    removed.add(previous)
                    edits[previous] = None
                previous_stores[key] = instruction.line
            elif instruction.op in {"load", "vload", "vstore"}:
                previous_stores.clear()
        if removed:
            blocks[label] = [instruction for instruction in block if instruction.line not in removed]
