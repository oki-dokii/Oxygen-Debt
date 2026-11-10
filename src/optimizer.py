"""Simplify KIR expressions and control flow, then remove dead computations."""

from collections import OrderedDict, deque
from operator import add, and_, eq, mul, or_, sub, xor

from .kirlib import MASK, SIGS, Instr
from .layout import choose_layout


BINARY = {
    "add": add, "sub": sub, "mul": mul, "and": and_, "or": or_, "xor": xor,
    "eq": eq, "lt": lambda a, b: (a ^ 0x80000000) < (b ^ 0x80000000),
    "shl": lambda a, b: a << (b & 31), "shr": lambda a, b: a >> (b & 31),
}
RIGHT_IDENTITY = {
    "add": 0, "sub": 0, "mul": 1, "and": MASK, "or": 0, "xor": 0,
    "shl": 0, "shr": 0,
}
COMMUTATIVE = {"add", "mul", "and", "or", "xor", "eq"}
PURE = BINARY.keys() | {"const", "mov", "select", "mac", "addsh"}
PROPAGATE = PURE | {"br", "ret"}
LIVENESS_BUDGET = 2_000_000


class BlockValues:
    """Associate registers with the values they currently hold."""

    def __init__(self):
        self.values = {}
        self.holders = {}

    def read(self, operand):
        kind, register = operand
        if kind != "r":
            return operand
        if register not in self.values:
            self.write(register, ("value", -register - 1))
        return self.values[register]

    def write(self, register, value):
        previous = self.values.get(register)
        if previous == value:
            return
        if previous is not None and previous[0] == "value":
            holders = self.holders[previous]
            del holders[register]
            if not holders:
                del self.holders[previous]
        self.values[register] = value
        if value[0] == "value":
            if value not in self.holders:
                self.holders[value] = OrderedDict()
            self.holders[value][register] = None

    def resolve(self, operand, shared_registers):
        value = self.read(operand)
        if value[0] != "value":
            return value
        if operand[1] in shared_registers:
            return operand
        return self.representative(value)

    def representative(self, value):
        holders = self.holders.get(value)
        return ("r", next(iter(holders))) if holders else None


def simplify(op, sources):
    if op == "select":
        cond, yes, no = sources
        if yes == no:
            return yes
        if cond[0] == "i":
            return yes if cond[1] else no
    if op not in BINARY:
        return None

    left, right = sources
    if left[0] == right[0] == "i":
        return ("i", int(BINARY[op](left[1], right[1])) & MASK)
    if left == right:
        if op in {"sub", "xor", "lt", "eq"}:
            return ("i", int(op == "eq"))
        if op in {"and", "or"}:
            return left
    if op in COMMUTATIVE and left[0] == "i":
        left, right = right, left
    if right[0] == "i":
        literal = right[1]
        if op in {"shl", "shr"}:
            literal &= 31
        if literal == RIGHT_IDENTITY.get(op):
            return left
        if (op in {"mul", "and"} and literal == 0) or (op == "or" and literal == MASK):
            return right
    return None


def simplify_block(instructions, machine, edits, shared_registers, may_spill):
    values = BlockValues()
    expressions = {}
    literal_memory = {}
    dynamic_memory = {}
    reuse_loads = machine["lat_alu"] <= machine["lat_load"]
    costly_spills = may_spill and machine["reg_spill_penalty"] > machine["lat_load"]
    last_effect = 0
    block = []
    for original in instructions:
        op = original.op
        args = original.args
        defines = SIGS[op].startswith("d")
        value = ("value", original.line)
        if op in PROPAGATE:
            args = [values.resolve(arg, shared_registers) if kind == "s" else arg
                    for kind, arg in zip(SIGS[op], args)]
            replacement = simplify(op, args[1:]) if defines else None
            cheap_copy = op != "mul" or machine["lat_alu"] <= machine["lat_mul"]
            if not cheap_copy:
                replacement = None
            if replacement is None and cheap_copy and (op in BINARY or op == "select"):
                operands = tuple(values.read(arg) for arg in args[1:])
                if op in COMMUTATIVE:
                    operands = tuple(sorted(operands))
                key = op, operands
                earlier = expressions.get(key)
                # A cheap recomputation can beat keeping a temporary live across an effect.
                if earlier and (not may_spill or op == "mul" or earlier[1] > last_effect):
                    replacement = values.representative(earlier)
                if replacement is None:
                    expressions[key] = value
            if replacement is not None:
                op = "const" if replacement[0] == "i" else "mov"
                args = [args[0], replacement]
            if op == "mov" and args[1][0] == "i":
                op = "const"
            if op == "br":
                condition, when_true, when_false = args
                if when_true == when_false:
                    op, args = "jmp", [when_true]
                elif condition[0] == "i":
                    op, args = "jmp", [when_true if condition[1] else when_false]
        elif reuse_loads and op in {"load", "store"}:
            address = values.read(args[1] if op == "load" else args[0])
            literal = address[0] == "i"
            memory = literal_memory if literal else dynamic_memory
            if op == "store":
                # Unknown addresses may alias anything. Distinct literals cannot alias.
                dynamic_memory.clear()
                if not literal:
                    literal_memory.clear()
                memory[address] = values.read(args[1])
            else:
                earlier = memory.get(address)
                if earlier is not None:
                    # Reaching here means the earlier access to this address succeeded.
                    source = None
                    if earlier[0] == "i":
                        source = earlier
                    elif not (costly_spills and (literal or args[0] == args[1])):
                        # Avoid adding a register touch to a single-register load.
                        source = values.representative(earlier)
                    if source is not None:
                        op = "const" if source[0] == "i" else "mov"
                        args = [args[0], source]
                if op == "load":
                    memory[address] = value

        if defines:
            if op in {"const", "mov"}:
                value = values.read(args[1])
            values.write(args[0][1], value)
        if op not in PROPAGATE:
            last_effect = original.line
        if op == "mov" and args[0] == args[1]:
            edits[original.line] = None
            continue
        if op != original.op or args != original.args:
            instruction = Instr(op, args, original.line, original.text)
            edits[original.line] = instruction
        else:
            instruction = original
        block.append(instruction)
    return block


def use_instruction(instruction, live):
    args = instruction.args
    if SIGS[instruction.op].startswith("d"):
        live.discard(args[0][1])
        args = args[1:]
    live.update(value for kind, value in args if kind == "r")


def scan_liveness(block, live, edits=None):
    for instruction in reversed(block):
        if instruction.op in PURE and instruction.args[0][1] not in live:
            if edits is not None:
                edits[instruction.line] = None
            continue
        use_instruction(instruction, live)
    return live


def combine_pair(producer, consumer, live, machine, may_spill):
    if consumer.op == "mov" and may_spill and producer.op in PURE:
        temp = producer.args[0]
        dest, source = consumer.args
        if temp == source and temp[1] not in live:
            return Instr(producer.op, [dest, *producer.args[1:]], consumer.line, consumer.text)

    if producer.op not in {"mul", "shl"} or consumer.op != "add":
        return None
    temp, left, right = producer.args
    dest, first, second = consumer.args
    if temp != dest and temp[1] in live:
        return None
    if (first == temp) == (second == temp):
        return None
    other = second if first == temp else first
    alu_latency = machine["lat_alu"]
    addsh_latency = machine["lat_addsh"]
    if producer.op == "shl":
        if right[0] == "i" and machine["fused_addsh"] and addsh_latency <= 2 * alu_latency:
            return Instr("addsh", [dest, other, left, ("k", right[1] & 31)], consumer.line, consumer.text)
        return None

    pair_latency = machine["lat_mul"] + alu_latency
    use_mac = machine["fused_mac"] and machine["lat_mac"] <= pair_latency
    if machine["fused_addsh"] and addsh_latency <= pair_latency and (
        not use_mac or addsh_latency < machine["lat_mac"]
    ):
        shifted, factor = (right, left) if left[0] == "i" else (left, right)
        if factor[0] == "i":
            multiplier = factor[1]
            if multiplier and (multiplier & (multiplier - 1)) == 0:
                args = [dest, other, shifted, ("k", multiplier.bit_length() - 1)]
                return Instr("addsh", args, consumer.line, consumer.text)
    if use_mac:
        return Instr("mac", [dest, left, right, other], consumer.line, consumer.text)
    return None


def combine_block(block, live, edits, machine, may_spill):
    consumer = block[-1]
    for producer in reversed(block[:-1]):
        if producer.line in edits and edits[producer.line] is None:
            continue
        combined = combine_pair(producer, consumer, live, machine, may_spill)
        if combined is None:
            use_instruction(consumer, live)
            consumer = producer
        else:
            edits[producer.line] = None
            edits[consumer.line] = combined
            consumer = combined


def branch_targets(block):
    return tuple(dict.fromkeys(value for kind, value in block[-1].args if kind == "l"))


def thread_jumps(blocks, edits):
    jumps = {
        label: block[-1].args[0][1]
        for label, block in blocks.items()
        if len(block) == 1 and block[-1].op == "jmp"
    }
    if not jumps:
        return

    destinations = {}
    for label in jumps:
        path = []
        target = label
        while target in jumps and target not in destinations:
            destinations[target] = None
            path.append(target)
            target = jumps[target]
        # Revisiting a pending jump means the path enters a cycle.
        destination = destinations.get(target, target)
        for hop in path:
            destinations[hop] = destination

    for block in blocks.values():
        original = block[-1]
        args = [
            (kind, destinations.get(value) or value) if kind == "l" else (kind, value)
            for kind, value in original.args
        ]
        if args == original.args:
            continue
        op = original.op
        if op == "br" and args[1] == args[2]:
            op, args = "jmp", [args[1]]
        replacement = Instr(op, args, original.line, original.text)
        block[-1] = replacement
        edits[original.line] = replacement


def remove_unreachable_blocks(blocks, program, edits):
    entry = program.block_labels[0]
    reachable = {entry}
    pending = [entry]
    while pending:
        for target in branch_targets(blocks[pending.pop()]):
            if target not in reachable:
                reachable.add(target)
                pending.append(target)

    for label in program.block_labels:
        if label not in reachable:
            edits[program.label_lines[label]] = None
            for instruction in blocks.pop(label):
                edits[instruction.line] = None


def remove_dead_code(blocks, edits, machine, may_spill):
    successors = {}
    predecessors = {label: [] for label in blocks}
    for label, block in blocks.items():
        targets = branch_targets(block)
        successors[label] = targets
        for target in targets:
            predecessors[target].append(label)

    live_in = {label: set() for label in blocks}
    pending = deque(reversed(blocks))
    queued = set(blocks)
    budget = LIVENESS_BUDGET

    def live_out(label):
        return set().union(*(live_in[target] for target in successors[label]))

    while pending:
        label = pending.popleft()
        queued.remove(label)
        budget -= (
            len(blocks[label]) + len(predecessors[label]) + len(live_in[label])
            + sum(len(live_in[target]) for target in successors[label])
        )
        if budget < 0:
            # With incomplete facts, only blocks that have no successors can be pruned.
            for terminal, block in blocks.items():
                if not successors[terminal]:
                    scan_liveness(block, set(), edits)
            return
        live = scan_liveness(blocks[label], live_out(label))
        if live != live_in[label]:
            live_in[label] = live
            for predecessor in predecessors[label]:
                if predecessor not in queued:
                    pending.append(predecessor)
                    queued.add(predecessor)

    for label, block in blocks.items():
        scan_liveness(block, live_out(label), edits)
        if may_spill or machine["fused_mac"] or machine["fused_addsh"]:
            combine_block(block, live_out(label), edits, machine, may_spill)


def render(source, edits, layout=None, label_lines=None):
    lines = source.splitlines(keepends=True)
    for number, replacement in edits.items():
        index = number - 1
        line = lines[index]
        body = line.splitlines()[0]
        statement, separator, comment = body.partition(";")
        indent = statement[:len(statement) - len(statement.lstrip())]
        ending = line[len(body):]
        if replacement is None:
            lines[index] = indent + separator + comment + ending if separator else ""
            continue
        args = ", ".join(f"v{value}" if kind == "r" else str(value)
                         for kind, value in replacement.args)
        suffix = f" ;{comment}" if separator else ""
        lines[index] = f"{indent}{replacement.op} {args}{suffix}{ending}"
    if layout is None:
        return "".join(lines)

    starts = sorted((label_lines[label] - 1, label) for label in layout)
    ends = [start for start, _ in starts[1:]] + [len(lines)]
    chunks = {label: "".join(lines[start:end]) for (start, label), end in zip(starts, ends)}
    parts = lines[:starts[0][0]]
    for label in layout[:-1]:
        chunk = chunks[label]
        parts.append(chunk if chunk.endswith(("\n", "\r")) else chunk + "\n")
    parts.append(chunks[layout[-1]])
    return "".join(parts)


def optimize(program, source, machine, profile=None):
    edits = {}
    blocks = {}
    registers = set(program.params)
    read_blocks = {}
    shared_registers = set()
    for instruction, label in zip(program.instrs, program.block_of):
        for kind, operand in zip(SIGS[instruction.op], instruction.args):
            if operand[0] == "r":
                register = operand[1]
                registers.add(register)
                if kind == "s" and read_blocks.setdefault(register, label) != label:
                    shared_registers.add(register)
    may_spill = len(registers) > machine["registers"] and machine["reg_spill_penalty"] > 0
    if not may_spill:
        shared_registers.clear()

    starts = [program.labels[label] for label in program.block_labels]
    ends = starts[1:] + [len(program.instrs)]
    for label, start, end in zip(program.block_labels, starts, ends):
        blocks[label] = simplify_block(
            program.instrs[start:end], machine, edits, shared_registers, may_spill,
        )
    thread_jumps(blocks, edits)
    remove_unreachable_blocks(blocks, program, edits)
    remove_dead_code(blocks, edits, machine, may_spill)
    layout = choose_layout(blocks, edits, machine, profile)
    return render(source, edits, layout, program.label_lines) if edits or layout else None
