"""Simplify KIR expressions and control flow, then remove dead computations."""

from collections import Counter, OrderedDict, deque

from .arithmetic import BINARY, COMMUTATIVE, simplify
from .branches import merge_straight_lines, select_assignments
from .kirlib import MASK, SIGS, Instr
from .layout import choose_layout
from .loops import double_loops, hoist_loops
from .memory import remove_overwritten_stores
from .ranges import entry_intervals, interval, reduce_division, update as update_interval
from .registers import compact_registers
from .summations import lower_summation
from .schedule import schedule_blocks
from .rolling import reuse_loop_loads


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


def simplify_block(instructions, machine, edits, shared_registers, may_spill, intervals, safe_memory):
    values = BlockValues()
    if intervals:
        for register, (low, high) in intervals.items():
            if low == high:
                values.write(register, ("i", low & MASK))
    expressions = {}
    negated_tests = {}
    literal_memory = {}
    dynamic_memory = {}
    address_keys = {}
    track_stores = any(instruction.op == "store" for instruction in instructions)
    reuse_loads = machine["lat_alu"] <= machine["lat_load"]
    reduce_divides = machine["lat_alu"] <= machine["lat_div"]
    costly_spills = may_spill and machine["reg_spill_penalty"] > machine["lat_load"]
    last_effect = 0
    block = []
    for original in instructions:
        op = original.op
        args = original.args
        defines = SIGS[op].startswith("d")
        value = ("value", original.line)
        if reduce_divides and intervals is not None and op in {"div", "mod"}:
            reduced = reduce_division(op, args, intervals)
            if reduced is not None:
                op, args = reduced
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
                else:
                    tested = negated_tests.get(values.read(condition))
                    if tested is not None:
                        operand, tested_value = tested
                        # Keep the original spelling when possible to avoid keeping a copy live.
                        source = (operand if values.read(operand) == tested_value
                                  else values.representative(tested_value))
                        if (source is not None and operand[1] not in shared_registers
                                and source[1] not in shared_registers):
                            args = [source, when_false, when_true]
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

        if intervals is not None and op in {"load", "store"}:
            operand = args[1] if op == "load" else args[0]
            lo, hi = interval(intervals, operand)
            if 0 <= lo <= hi < 4096:
                key = ("i", lo) if lo == hi else values.read(operand)
                safe_memory[original.line] = address_keys.get(key, key)
        if track_stores and op == "add":
            # Match repeated address additions without extending the register's lifetime.
            address_keys[value] = ("add", *sorted(values.read(arg) for arg in args[1:]))
        if defines:
            if op == "eq":
                left, right = args[1:]
                if right == ("i", 0):
                    negated_tests[value] = left, values.read(left)
                elif left == ("i", 0):
                    negated_tests[value] = right, values.read(right)
            if intervals is not None:
                update_interval(intervals, op, args)
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


def scan_liveness(block, live, safe_memory, edits=None):
    for instruction in reversed(block):
        discardable = instruction.op in PURE or (
            instruction.op == "load" and instruction.line in safe_memory
        )
        if discardable and instruction.args[0][1] not in live:
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


def thread_jumps(blocks, edits, order=None, profile=None):
    jumps = {
        label: block[-1].args[0][1]
        for label, block in blocks.items()
        if len(block) == 1 and block[-1].op == "jmp"
    }
    if not jumps and not order:
        return False

    following = dict(zip(order, order[1:])) if order else {}
    incoming = Counter(target for block in blocks.values() for target in branch_targets(block)) if order else {}

    destinations = {}
    for label in jumps:
        path = []
        target = label
        while target in jumps and target not in destinations:
            destinations[target] = None
            path.append(target)
            target = jumps[target]
        # Revisiting a pending jump means the path enters a cycle.
        route = destinations.get(target, (target, False, True))
        for hop in reversed(path):
            if route is not None and order:
                endpoint, taken, exclusive = route
                route = (endpoint, taken or following.get(hop) != jumps[hop],
                         exclusive and incoming[hop] == 1 and hop != order[0])
            destinations[hop] = route

    def redirect(origin, target):
        route = destinations.get(target)
        if route is None:
            return target
        endpoint, taken, exclusive = route
        if order and following.get(origin) == target and not (taken or exclusive):
            # A shared chain of fallthroughs could stay in the file after this edge changes.
            return target
        return endpoint

    changed = False
    for label, block in blocks.items():
        original = block[-1]
        args = [
            (kind, redirect(label, value)) if kind == "l" else (kind, value)
            for kind, value in original.args
        ]
        op = original.op
        if order and op == "jmp":
            target = blocks[args[0][1]]
            if len(target) == 1 and target[0].op == "ret":
                op, args = "ret", target[0].args
        if op == original.op and args == original.args:
            continue
        if profile:
            for old, new in zip(original.args, args):
                if old[0] == new[0] == "l" and old != new:
                    weight = profile.pop((label, old[1]), 0)
                    if weight:
                        edge = label, new[1]
                        profile[edge] = profile.get(edge, 0) + weight
        # The late pass preserves register touches after allocation.
        if order is None and op == "br" and args[1] == args[2]:
            op, args = "jmp", [args[1]]
        replacement = Instr(op, args, original.line, original.text)
        block[-1] = replacement
        edits[original.line] = replacement
        changed = True
    return changed


def remove_unreachable_blocks(blocks, program, edits):
    entry = program.block_labels[0]
    reachable = {entry}
    pending = [entry]
    while pending:
        for target in branch_targets(blocks[pending.pop()]):
            if target not in reachable:
                reachable.add(target)
                pending.append(target)

    for label in tuple(blocks):
        if label not in reachable:
            edits[program.label_lines[label]] = None
            for instruction in blocks.pop(label):
                edits[instruction.line] = None


def remove_dead_code(blocks, edits, machine, may_spill, safe_memory):
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
                    scan_liveness(block, set(), safe_memory, edits)
            return
        live = scan_liveness(blocks[label], live_out(label), safe_memory)
        if live != live_in[label]:
            live_in[label] = live
            for predecessor in predecessors[label]:
                if predecessor not in queued:
                    pending.append(predecessor)
                    queued.add(predecessor)

    for label, block in blocks.items():
        scan_liveness(block, live_out(label), safe_memory, edits)
        if may_spill or machine["fused_mac"] or machine["fused_addsh"]:
            combine_block(block, live_out(label), edits, machine, may_spill)
    return live_in


def format_instruction(instruction):
    args = ", ".join(f"v{value}" if kind == "r" else str(value)
                     for kind, value in instruction.args)
    return f"{instruction.op} {args}"


def render(source, edits, layout=None, label_lines=None, placement=None, expansions=None):
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
        suffix = f" ;{comment}" if separator else ""
        lines[index] = f"{indent}{format_instruction(replacement)}{suffix}{ending}"
    if expansions:
        default_ending = lines[0][len(lines[0].splitlines()[0]):] or "\n"
        for anchor, instructions in expansions.items():
            line = lines[anchor - 1]
            body = line.splitlines()[0]
            statement, separator, comment = body.partition(";")
            indent = statement[:len(statement) - len(statement.lstrip())]
            ending = line[len(body):]
            emitted = [
                f"{item}:" if isinstance(item, str) else indent + format_instruction(item)
                for item in instructions
            ]
            if separator:
                emitted[1] += f" ;{comment}"
            lines[anchor - 1] = (ending or default_ending).join(emitted) + ending
    if placement:
        insertions = {}
        for origin, anchor in placement.items():
            insertions.setdefault(anchor, []).append(lines[origin - 1])
            lines[origin - 1] = ""
        for anchor, moved in insertions.items():
            lines[anchor - 1] = "".join(moved) + lines[anchor - 1]
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


def render_canonical(program, blocks, order, expansions):
    params = ", ".join(f"v{register}" for register in program.params)
    lines = [f"func {program.name}({params})"]
    for label in order:
        lines.append(f"{label}:")
        for instruction in blocks[label]:
            for item in expansions.get(instruction.line, (instruction,)):
                lines.append(f"{item}:" if isinstance(item, str) else "  " + format_instruction(item))
    return "\n".join(lines) + "\n"


def optimize(program, source, machine, profile=None):
    edits = {}
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
    blocks = {
        label: program.instrs[start:end]
        for label, start, end in zip(program.block_labels, starts, ends)
    }
    range_ops = {"load", "store"}
    if machine["lat_alu"] <= machine["lat_div"]:
        range_ops.update(("div", "mod"))
    use_intervals = len(blocks) > 1 or any(instruction.op in range_ops for instruction in program.instrs)
    intervals = entry_intervals(blocks) if use_intervals else {}
    safe_memory = {}
    for label, block in blocks.items():
        facts = intervals.get(label, {}).copy() if use_intervals else None
        blocks[label] = simplify_block(block, machine, edits, shared_registers, may_spill, facts, safe_memory)
    profile = profile.copy() if profile else None
    thread_jumps(blocks, edits, profile=profile)
    remove_unreachable_blocks(blocks, program, edits)
    if safe_memory:
        remove_overwritten_stores(blocks, edits, safe_memory)
    placement = select_assignments(blocks, edits)
    if placement:
        remove_unreachable_blocks(blocks, program, edits)
    placement.update(hoist_loops(blocks, PURE))
    live_in = remove_dead_code(blocks, edits, machine, may_spill, safe_memory)
    retained = {
        label: [current for instruction in block
                if (current := edits.get(instruction.line, instruction)) is not None]
        for label, block in blocks.items()
    }
    summed = lower_summation(retained, machine, max(ins.line for ins in program.instrs) + 1)
    if summed is not None:
        blocks = retained
        for instruction in blocks[summed]:
            edits[instruction.line] = instruction
        facts = intervals.get(summed, {}).copy() if use_intervals else None
        blocks[summed] = simplify_block(blocks[summed], machine, edits, shared_registers,
                                        may_spill, facts, safe_memory)
        remove_unreachable_blocks(blocks, program, edits)
        live_in = remove_dead_code(blocks, edits, machine, may_spill, safe_memory)
    if may_spill and live_in is not None:
        compact_registers(blocks, edits, live_in, program.params, machine)
    layout = choose_layout(blocks, edits, machine, profile)
    blocks = {
        label: [current for instruction in block
                if (current := edits.get(instruction.line, instruction)) is not None]
        for label, block in blocks.items()
    }
    if thread_jumps(blocks, edits, layout or list(blocks)):
        remove_unreachable_blocks(blocks, program, edits)
        if layout:
            layout = [label for label in layout if label in blocks]
    if merge_straight_lines(blocks, edits, program.label_lines, layout or list(blocks)):
        if layout:
            layout = [label for label in layout if label in blocks]
    rolling = reuse_loop_loads(blocks, layout or list(blocks), program.params, machine, PURE)
    scheduled = schedule_blocks(blocks, layout or list(blocks), program.params, machine)
    expansions = double_loops(blocks, layout or list(blocks), machine)
    if summed is not None or scheduled or rolling:
        return render_canonical(program, blocks, layout or list(blocks), expansions)
    if edits or layout or placement or expansions:
        return render(source, edits, layout, program.label_lines, placement, expansions)
    return None
