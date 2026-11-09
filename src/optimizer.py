"""Local simplification and removal of dead, non-trapping instructions."""

from collections import OrderedDict, deque
from operator import add, and_, eq, mul, or_, sub, xor

from .kirlib import MASK, SIGS, Instr


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
        if value[0] == "value":
            if operand[1] in shared_registers:
                return operand
            return ("r", next(iter(self.holders[value])))
        return value


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


def simplify_block(instructions, machine, edits, shared_registers):
    values = BlockValues()
    block = []
    for original in instructions:
        op = original.op
        args = original.args
        defines = SIGS[op].startswith("d")
        if op in PROPAGATE:
            args = [values.resolve(arg, shared_registers) if kind == "s" else arg
                    for kind, arg in zip(SIGS[op], args)]
            replacement = simplify(op, args[1:]) if defines else None
            if op == "mul" and machine["lat_alu"] > machine["lat_mul"]:
                replacement = None
            if replacement is not None:
                op = "const" if replacement[0] == "i" else "mov"
                args = [args[0], replacement]
            if op == "mov" and args[1][0] == "i":
                op = "const"

        if defines:
            value = values.read(args[1]) if op in {"const", "mov"} else ("value", original.line)
            values.write(args[0][1], value)
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


def scan_liveness(block, live, edits=None):
    for instruction in reversed(block):
        args = instruction.args
        if SIGS[instruction.op].startswith("d"):
            dest = args[0][1]
            if dest not in live and instruction.op in PURE:
                if edits is not None:
                    edits[instruction.line] = None
                continue
            live.discard(dest)
            args = args[1:]
        live.update(value for kind, value in args if kind == "r")
    return live


def remove_dead_code(blocks, edits):
    successors = {}
    predecessors = {label: [] for label in blocks}
    for label, block in blocks.items():
        targets = tuple(dict.fromkeys(value for kind, value in block[-1].args if kind == "l"))
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


def render(source, edits):
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
    return "".join(lines)


def optimize(program, source, machine):
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
    if len(registers) <= machine["registers"]:
        shared_registers.clear()

    starts = [program.labels[label] for label in program.block_labels]
    ends = starts[1:] + [len(program.instrs)]
    for label, start, end in zip(program.block_labels, starts, ends):
        blocks[label] = simplify_block(program.instrs[start:end], machine, edits, shared_registers)
    remove_dead_code(blocks, edits)
    return render(source, edits) if edits else None
