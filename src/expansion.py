"""Expand a bounded, statically known control path without inspecting memory."""

from collections import OrderedDict

from .arithmetic import BINARY, simplify
from .kirlib import MASK, SIGS


def expand(program):
    """Return straight-line KIR only if every encountered branch is proved.

    Known registers hold exact word constants; parameters and effect results
    are unknown. All effects (including possible traps) stay in original order.
    Exhausting either budget or encountering an unknown branch rejects the
    entire candidate. Nothing from RAM or a profile supplies a static fact.
    """
    if len(program.instrs) > 500 or len(program.block_labels) < 2:
        return None
    known = {register: None for register in program.params}
    output = []
    pc = 0
    repeated = False
    visited = set()
    for _ in range(16_384):
        repeated |= pc in visited
        visited.add(pc)
        ins = program.instrs[pc]
        op = ins.op
        args = [(("i", known.get(value, 0)) if kind == "s" and tag == "r"
                 and known.get(value, 0) is not None else (tag, value))
                for kind, (tag, value) in zip(SIGS[op], ins.args)]
        if op in {"jmp", "br"}:
            if op == "br" and args[0][0] != "i":
                return None
            target = args[0] if op == "jmp" else args[1 if args[0][1] else 2]
            next_pc = program.labels[target[1]]
            pc = next_pc
            continue
        if SIGS[op].startswith("d"):
            sources = args[1:]
            folded = None
            if op in {"const", "mov"}:
                folded = sources[0]
            elif op in BINARY or op == "select":
                folded = simplify(op, sources)
            elif op in {"mac", "addsh"} and all(tag in {"i", "k"} for tag, _ in sources):
                a, b, c = (value for _, value in sources)
                folded = ("i", (a*b+c if op == "mac" else a+(b << c)) & MASK)
            known[args[0][1]] = folded[1] if folded is not None and folded[0] == "i" else None
            if known[args[0][1]] is not None:
                pc += 1
                continue
            if folded is not None:
                op, args = "mov", [args[0], folded]
        output.append("  " + op + " " + ", ".join(
            f"v{value}" if tag == "r" else str(value) for tag, value in args))
        if len(output) > 2_048:
            return None
        if op in {"ret", "trap"}:
            if not repeated:
                return None
            params = ", ".join(f"v{r}" for r in program.params)
            return f"func {program.name}({params})\n{program.block_labels[0]}:\n" + "\n".join(output) + "\n"
        pc += 1
    return None


def cache_loads(program, capacity):
    """Rename one expanded block and retain a bounded cache of RAM values.

    A cached load must already have succeeded on the sole execution
    path. Unknown stores invalidate everything; literal stores invalidate the
    matching word. Fresh definitions keep saved values alive through mutable
    source-register overwrites. Later allocation handles their lifetimes.
    """
    if len(program.block_labels) != 1 or len(program.instrs) > 2_048:
        return None
    current = {register: ("r", register) for register in program.params}
    next_register = max(program.params, default=-1) + 1
    memory = OrderedDict()
    output = []
    reused = False
    for ins in program.instrs:
        if ins.op in {"br", "jmp"}:
            return None
        args = [current.get(value, ("i", 0)) if kind == "s" and tag == "r" else (tag, value)
                for kind, (tag, value) in zip(SIGS[ins.op], ins.args)]
        if ins.op == "load" and args[1][0] == "i" and args[1][1] in memory:
            address = args[1][1]
            current[ins.args[0][1]] = memory[address]
            memory.move_to_end(address)
            reused = True
            continue
        if ins.op in {"const", "mov"}:
            current[ins.args[0][1]] = args[1]
            continue
        if SIGS[ins.op].startswith("d"):
            if next_register > 999_999:
                return None
            dest = ("r", next_register)
            next_register += 1
            current[ins.args[0][1]] = dest
            args[0] = dest
        if ins.op == "store":
            if args[0][0] == "i":
                memory.pop(args[0][1], None)
            else:
                memory.clear()
        elif ins.op == "load" and args[1][0] == "i":
            memory[args[1][1]] = args[0]
            if len(memory) > capacity:
                memory.popitem(last=False)
        output.append("  " + ins.op + " " + ", ".join(
            f"v{value}" if tag == "r" else str(value) for tag, value in args))
    if not reused:
        return None
    params = ", ".join(f"v{r}" for r in program.params)
    return f"func {program.name}({params})\n{program.block_labels[0]}:\n" + "\n".join(output) + "\n"
