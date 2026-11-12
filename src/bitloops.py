"""Prove fixed-trip bit loops using word expressions and GF(2) coefficients."""

from .arithmetic import simplify
from .kirlib import MASK, Instr, SIGS
from .ranges import entry_intervals, interval, update
from .registers import register_reads, register_names

BITS = 32


class Reject(Exception):
    pass


def constant(word):
    return tuple((word >> bit) & 1 for bit in range(BITS))


def literal(vector):
    return sum(bit << i for i, bit in enumerate(vector)) if all(bit <= 1 for bit in vector) else None


def operate(op, args):
    numbers = [literal(value) for value in args]
    folded = simplify(op, [("i", value) for value in numbers]) if all(value is not None for value in numbers) else None
    if folded is not None:
        return constant(folded[1])
    if op in {"mov", "const"}:
        return args[0]
    if op == "xor":
        return tuple(a ^ b for a, b in zip(*args))
    if op in {"and", "or"}:
        result = []
        for a, b in zip(*args):
            if a == b:
                result.append(a)
            elif op == "and" and (not a or not b):
                result.append(0)
            elif op == "or" and (a == 1 or b == 1):
                result.append(1)
            elif a <= 1:
                result.append(b)
            elif b <= 1:
                result.append(a)
            else:
                raise Reject()
        return tuple(result)
    if op in {"shl", "shr"} and numbers[1] is not None:
        shift = numbers[1] & 31
        if not shift:
            return args[0]
        return ((0,) * shift + args[0][:-shift] if op == "shl"
                else args[0][shift:] + (0,) * shift)
    if op in {"add", "sub", "mul"}:
        if op in {"add", "sub"} and numbers[1] == 0:
            return args[0]
        if op == "add" and numbers[0] == 0:
            return args[1]
        if op == "mul":
            for i in (0, 1):
                n = numbers[i]
                if n == 0:
                    return constant(0)
                if n is not None and n & (n - 1) == 0:
                    return operate("shl", [args[1-i], constant(n.bit_length()-1)])
    if op == "eq":
        for i in (0, 1):
            if numbers[i] in (0, 1) and not any(args[1-i][1:]):
                return (args[1-i][0] ^ (numbers[i] ^ 1),) + (0,) * 31
    if op == "select":
        return choose(args[0], args[1], args[2])
    if op == "addsh":
        return operate("add", [args[0], operate("shl", args[1:])])
    raise Reject()


def choose(condition, yes, no):
    value = literal(condition)
    if value is not None:
        return yes if value else no
    if any(condition[1:]):
        raise Reject()
    result = []
    for a, b in zip(yes, no):
        difference = a ^ b
        if difference > 1:
            raise Reject()
        result.append(b ^ (condition[0] if difference else 0))
    return tuple(result)


class WordEmitter:
    def __init__(self, register, line):
        self.register, self.line = register, line
        self.instructions = []

    def emit(self, op, *sources):
        if self.register >= 1_000_000:
            raise Reject()
        dest = ("r", self.register)
        self.register += 1
        self.instructions.append(Instr(op, [dest, *sources], self.line, ""))
        self.line += 1
        return dest

    def reverse(self, source):
        for shift, mask in ((1, 0x55555555), (2, 0x33333333), (4, 0x0F0F0F0F), (8, 0x00FF00FF)):
            right = self.emit("shr", source, ("i", shift))
            right = self.emit("and", right, ("i", mask))
            left = self.emit("and", source, ("i", mask))
            left = self.emit("shl", left, ("i", shift))
            source = self.emit("or", left, right)
        return self.emit("or", self.emit("shr", source, ("i", 16)), self.emit("shl", source, ("i", 16)))

    def popcount(self, source, mask):
        if mask != MASK:
            source = self.emit("and", source, ("i", mask))
        shifted = self.emit("shr", source, ("i", 1))
        source = self.emit("sub", source, self.emit("and", shifted, ("i", 0x55555555)))
        shifted = self.emit("and", self.emit("shr", source, ("i", 2)), ("i", 0x33333333))
        source = self.emit("add", self.emit("and", source, ("i", 0x33333333)), shifted)
        source = self.emit("and", self.emit("add", source, self.emit("shr", source, ("i", 4))), ("i", 0x0F0F0F0F))
        source = self.emit("mul", source, ("i", 0x01010101))
        return self.emit("shr", source, ("i", 24))

    def vector(self, vector, variables):
        const = sum((bit & 1) << i for i, bit in enumerate(vector))
        columns = {}
        for output, value in enumerate(vector):
            value >>= 1
            while value:
                low = value & -value
                index = low.bit_length() - 1
                columns[index] = columns.get(index, 0) | (1 << output)
                value ^= low
        # A reflection permutation is emitted with word-parallel bit swaps.
        if columns and all(column & (column - 1) == 0 for column in columns.values()):
            reflections = [(variables[index][0], variables[index][1] + column.bit_length() - 1)
                           for index, column in columns.items()]
            if len(columns) >= 8 and len(set(reflections)) == 1:
                register, center = reflections[0]
                result = self.reverse(("r", register))
                if center != 31:
                    result = self.emit("shl" if center > 31 else "shr", result, ("i", abs(center - 31)))
                mask = sum(columns.values())
                if mask != MASK:
                    result = self.emit("and", result, ("i", mask))
                return self.emit("xor", result, ("i", const)) if const else result
        groups, dense = {}, []
        for index, column in sorted(columns.items()):
            register, bit = variables[index]
            if column & (column - 1) == 0:
                key = register, column.bit_length() - 1 - bit
                groups[key] = groups.get(key, 0) | (1 << bit)
            else:
                dense.append((register, bit, column))
        result = ("i", const)
        for (register, delta), mask in sorted(groups.items()):
            term = ("r", register)
            implied = MASK if delta == 0 else ((MASK >> delta) if delta > 0 else (MASK << -delta) & MASK)
            if mask != implied:
                term = self.emit("and", term, ("i", mask))
            if delta:
                term = self.emit("shl" if delta > 0 else "shr", term, ("i", abs(delta)))
            result = term if result == ("i", 0) else self.emit("xor", result, term)
        for register, bit, column in dense:
            term = ("r", register)
            if bit:
                term = self.emit("shr", term, ("i", bit))
            term = self.emit("and", term, ("i", 1))
            term = self.emit("sub", ("i", 0), term)
            term = self.emit("and", term, ("i", column))
            result = term if result == ("i", 0) else self.emit("xor", result, term)
        return result


def synthesize(blocks, pure):
    """Replace one proven fixed-trip bit loop; return its preheader or None."""
    if sum(map(len, blocks.values())) > 5000:
        return None
    predecessors = {label: [] for label in blocks}
    for label, block in blocks.items():
        for target in dict.fromkeys(v for kind, v in block[-1].args if kind == "l"):
            predecessors[target].append(label)
    incoming = entry_intervals(blocks)
    for head, header in blocks.items():
        if head == next(iter(blocks)) or len(header) != 2 or header[0].op != "lt" or header[1].op != "br":
            continue
        condition, counter, bound = header[0].args
        if counter[0] != "r" or condition == counter or header[1].args[0] != condition:
            continue
        body, exit_label = (arg[1] for arg in header[1].args[1:])
        region, pending = set(), [body]
        while pending and len(region) <= 16:
            label = pending.pop()
            if label in (head, exit_label) or label in region:
                continue
            region.add(label)
            pending.extend(v for kind, v in blocks[label][-1].args if kind == "l")
        if (pending or not region or exit_label in region or next(iter(blocks)) in region
                or sum(len(blocks[label]) for label in region) > 96):
            continue
        outsiders = [label for label in predecessors[head] if label not in region]
        if len(outsiders) != 1 or blocks[outsiders[0]][-1].op != "jmp":
            continue
        preheader = outsiders[0]
        if any(pred not in region | {head} for label in region for pred in predecessors[label]):
            continue
        if any(ins.op not in pure | {"jmp", "br"} for label in region for ins in blocks[label]):
            continue
        written = {ins.args[0][1] for label in region | {head} for ins in blocks[label] if SIGS[ins.op].startswith("d")}
        if bound[0] == "r" and bound[1] in written:
            continue
        facts = incoming.get(preheader, {}).copy()
        for ins in blocks[preheader][:-1]:
            update(facts, ins.op, ins.args)
        start, start_hi = interval(facts, counter)
        stop, stop_hi = interval(facts, bound)
        if start != start_hi or stop != stop_hi or not 0 <= start < stop <= 32:
            continue
        observed = {r for label, block in blocks.items() if label not in region | {head}
                    for ins in block for r in register_reads(ins)} & written
        live = {label: set() for label in region | {head}}
        for _ in range(128):
            updated = False
            for label in live:
                needed = set()
                for kind, target in blocks[label][-1].args:
                    if kind == "l": needed.update(live.get(target, observed))
                for ins in reversed(blocks[label]):
                    if SIGS[ins.op].startswith("d"): needed.discard(ins.args[0][1])
                    needed.update(register_reads(ins))
                if needed != live[label]: live[label] = needed; updated = True
            if not updated: break
        else:
            continue
        live_at_head = live[head] | observed
        emitter = WordEmitter(max(register_names(ins for block in blocks.values() for ins in block), default=-1)+1,
                              max(ins.line for block in blocks.values() for ins in block)+1)
        try:
            # First recognize a population sum by symbolic word expressions.
            if len(region) == 1 and blocks[body][-1].op == "jmp" and blocks[body][-1].args == [("l", head)]:
                label = next(iter(region)); expr = {r: ("v", r) for r in written}
                def read_expr(arg):
                    if arg[0] != "r": return ("i", arg[1])
                    return expr.get(arg[1], ("v", arg[1]))
                for ins in blocks[label][:-1]:
                    args = [read_expr(arg) for arg in ins.args[1:]]
                    if ins.op in {"const", "mov"}: value = args[0]
                    else:
                        value = (ins.op, *sorted(args)) if ins.op in {"add", "and"} else (ins.op, *args)
                    expr[ins.args[0][1]] = value
                expected_step = ("add", *sorted([("v", counter[1]), ("i", 1)]))
                if expr.get(counter[1]) == expected_step:
                    for accumulator in sorted(observed - {counter[1], condition[1]}):
                        value = expr.get(accumulator)
                        if value is None or value[0] != "add" or ("v", accumulator) not in value[1:]: continue
                        term = value[2] if value[1] == ("v", accumulator) else value[1]
                        if term[0] != "and" or ("i", 1) not in term[1:]: continue
                        shift = term[2] if term[1] == ("i", 1) else term[1]
                        if shift[0] != "shr" or shift[2] != ("v", counter[1]) or shift[1][0] != "v" or shift[1][1] in written: continue
                        if observed - {accumulator, counter[1], condition[1]}: continue
                        mask = ((1 << stop) - 1) ^ ((1 << start) - 1)
                        count = emitter.popcount(("r", shift[1][1]), mask)
                        initial = interval(facts, ("r", accumulator))
                        original = ("i", initial[0] & MASK) if initial[0] == initial[1] else ("r", accumulator)
                        result = count if original == ("i", 0) else emitter.emit("add", original, count)
                        outputs = {accumulator: result, counter[1]: ("i", stop), condition[1]: ("i", 0)}
                        for r in sorted(observed):
                            emitter.instructions.append(Instr("mov" if outputs[r][0] == "r" else "const", [("r",r), outputs[r]], emitter.line, "")); emitter.line += 1
                        break
            if not emitter.instructions:
                variables, initial = [], {}
                for r, (lo, hi) in facts.items():
                    if lo == hi: initial[r] = constant(lo & MASK)
                def initial_value(r):
                    if r not in initial:
                        if len(variables) >= 256: raise Reject()
                        offset = len(variables)
                        variables.extend((r, bit) for bit in range(32))
                        initial[r] = tuple(1 << (offset+bit+1) for bit in range(32))
                    return initial[r]
                state = initial.copy()
                def read(state, arg):
                    return (state[arg[1]] if arg[1] in state else initial_value(arg[1])) if arg[0] == "r" else constant(arg[1])
                visits = [0]
                def execute(label, state, seen):
                    if label == head: return state
                    if label not in region or label in seen: raise Reject()
                    seen = seen | {label}; state = state.copy()
                    visits[0] += len(blocks[label])
                    if visits[0] > 8192: raise Reject()
                    for ins in blocks[label][:-1]:
                        state[ins.args[0][1]] = operate(ins.op, [read(state,arg) for arg in ins.args[1:]])
                    branch = blocks[label][-1]
                    if branch.op == "jmp": return execute(branch.args[0][1], state, seen)
                    test = read(state, branch.args[0]); known = literal(test)
                    if known is not None: return execute(branch.args[1 if known else 2][1], state, seen)
                    yes = execute(branch.args[1][1], state, seen); no = execute(branch.args[2][1], state, seen)
                    return {r: choose(test, yes[r] if r in yes else initial_value(r), no[r] if r in no else initial_value(r)) for r in live_at_head}
                for i in range(start, stop):
                    state[condition[1]] = constant(1)
                    state = execute(body, state, set())
                    if literal(read(state,counter)) != i+1: raise Reject()
                state[condition[1]] = constant(0)
                outputs = []
                for r in sorted(observed):
                    value = emitter.vector(state[r] if r in state else initial_value(r), variables)
                    if value[0] == "r" and value[1] in written:
                        value = emitter.emit("mov", value)
                    outputs.append((r, value))
                # Compute every expression before any original register is overwritten.
                for r, value in outputs:
                    emitter.instructions.append(Instr("mov" if value[0] == "r" else "const", [("r",r), value], emitter.line, "")); emitter.line += 1
            if len(emitter.instructions) > 256: raise Reject()
        except (Reject, RecursionError):
            continue
        jump = blocks[preheader][-1]
        blocks[preheader][-1:] = [*emitter.instructions, Instr("jmp", [("l",exit_label)], jump.line, jump.text)]
        return preheader
    return None
