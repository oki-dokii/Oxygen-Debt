"""Exhaustively specialize pure programs with a proven small input domain."""

from .kiln import compile_program, execute, time_trace
from .kirlib import SIGS, parse_program

EVALUATION_BUDGET = 2_000_000
MAX_BITS = 12
COST_BUDGET = 2_000_000


def masked_parameter(program):
    parameters = set(program.params)
    used = {
        value for ins in program.instrs for kind, (operand, value) in zip(SIGS[ins.op], ins.args)
        if kind == "s" and operand == "r" and value in parameters
    }
    if not 1 <= len(used) <= 2:
        return None
    entry_end = (program.labels[program.block_labels[1]]
                 if len(program.block_labels) > 1 else len(program.instrs))
    raw = set(used)
    masks = dict.fromkeys(sorted(used), 0)
    for instruction in program.instrs[:entry_end]:
        reads = [operand for kind, operand in zip(SIGS[instruction.op], instruction.args) if kind == "s"]
        for parameter in sorted(raw):
            if ("r", parameter) in reads:
                if instruction.op != "and":
                    return None
                left, right = instruction.args[1:]
                other = right if left == ("r", parameter) else left
                if other[0] != "i":
                    return None
                masks[parameter] |= other[1]
        if SIGS[instruction.op].startswith("d"):
            raw.discard(instruction.args[0][1])
    if any(kind == "s" and operand[0] == "r" and operand[1] in raw
           for ins in program.instrs[entry_end:] for kind, operand in zip(SIGS[ins.op], ins.args)):
        return None
    positions = [(register, bit) for register, mask in masks.items() for bit in range(32) if mask & (1 << bit)]
    return positions if len(positions) <= MAX_BITS else None


def lookup_source(program, positions, outputs, packed):
    width = max(1, max(outputs).bit_length())
    group_bits = min(len(positions), (32 // width).bit_length() - 1) if packed else 0
    parameter = positions[0][0] if positions else program.params[0]
    if positions[:group_bits] != [(parameter, bit) for bit in range(group_bits)]:
        group_bits = 0
    size = 1 << group_bits
    words = [
        sum(value << (offset * width) for offset, value in enumerate(outputs[start:start + size]))
        for start in range(0, len(outputs), size)
    ]
    nodes = []
    interned = {}

    def intern(key):
        if key not in interned:
            interned[key] = len(nodes)
            nodes.append(key)
        return interned[key]

    def build(values, bit):
        if all(value == values[0] for value in values):
            return intern(("leaf", values[0]))
        half = len(values) // 2
        no = build(values[:half], bit - 1)
        yes = build(values[half:], bit - 1)
        return no if yes == no else intern(("test", positions[bit], yes, no))

    root = build(words, len(positions) - 1)
    available = (register for register in range(1_000_000) if register not in program.params)
    index, condition, result = (f"v{next(available)}" for _ in range(3))
    params = ", ".join(f"v{register}" for register in program.params)
    lines = [f"func {program.name}({params})", "finite_entry:"]
    if group_bits:
        lines.append(f"  and {index}, v{parameter}, {(1 << group_bits) - 1}")
        if width > 1:
            op = "shl" if width & (width - 1) == 0 else "mul"
            amount = width.bit_length() - 1 if op == "shl" else width
            lines.append(f"  {op} {index}, {index}, {amount}")
    seen = set()

    def emit(node):
        if node in seen:
            return
        seen.add(node)
        if node != root:
            lines.append(f"finite_{node}:")
        entry = nodes[node]
        if entry[0] == "leaf":
            if group_bits:
                lines.extend((f"  shr {result}, {entry[1]}, {index}",
                              f"  and {result}, {result}, {(1 << width) - 1}", f"  ret {result}"))
            else:
                lines.append(f"  ret {entry[1]}")
            return
        _, (register, bit), yes, no = entry
        target = lambda n: "finite_entry" if n == root else f"finite_{n}"
        lines.extend((f"  and {condition}, v{register}, {1 << bit}",
                      f"  br {condition}, {target(yes)}, {target(no)}"))
        emit(no)
        emit(yes)

    emit(root)
    return "\n".join(lines) + "\n"


def specialize(program, machine):
    if len(program.instrs) > 5000 or any(
        instruction.op in {"load", "store", "vload", "vstore", "trap"} for instruction in program.instrs
    ):
        return None
    proved = masked_parameter(program)
    if proved is None:
        return None
    positions = proved
    original = compile_program(program)
    representatives = []
    for number in range(1 << len(positions)):
        words = dict.fromkeys(program.params, 0)
        for index, (register, bit) in enumerate(positions):
            words[register] |= ((number >> index) & 1) << bit
        representatives.append([words[register] for register in program.params])
    budget = EVALUATION_BUDGET
    outputs = []
    inputs = []
    best_score = 1
    cost_budget = COST_BUDGET
    for args in representatives:
        run = execute(original, args, [], {}, min(20_000, budget), want_trace=True)
        budget -= run.steps
        if run.status != "RET" or budget <= 0:
            return None
        outputs.append(run.value)
        inputs.append(args)
        cost_budget -= len(original.code) + len(run.trace)
        if cost_budget < 0:
            return None
        best_score *= time_trace(original, run.trace, machine)
    best = None
    tested = set()
    for packed in (False, True):
        source = lookup_source(program, positions, outputs, packed)
        if source in tested:
            continue
        tested.add(source)
        parsed = parse_program(source)
        if len(parsed.instrs) > 4096 or len(parsed.instrs) * len(inputs) > cost_budget:
            continue
        candidate = compile_program(parsed)
        score = 1
        for args, expected in zip(inputs, outputs):
            run = execute(candidate, args, [], {}, 1000, want_trace=True)
            if run.status != "RET" or run.value != expected:
                raise ValueError("finite specialization failed its exhaustive check")
            cost_budget -= len(candidate.code) + len(run.trace)
            if cost_budget < 0:
                return best
            score *= time_trace(candidate, run.trace, machine)
        if score < best_score:
            best_score = score
            best = source
    return best
