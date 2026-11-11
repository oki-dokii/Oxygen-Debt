"""Prove and lower bounded polynomial summations over a counting loop."""

from collections import Counter

from .kirlib import MASK, Instr, SIGS
from .ranges import MAX, entry_intervals, interval, signed, update

INVERSE_THREE = 0xAAAAAAAB  # 3 * INVERSE_THREE == 1 modulo 2**32.


def combine(left, right, multiply=False, subtract=False):
    if not isinstance(left, dict) or not isinstance(right, dict):
        return None
    result = {}
    if multiply:
        for (i, a), x in left.items():
            for (j, b), y in right.items():
                if i + j + a + b > 3:
                    return None
                term = i + j, a + b
                result[term] = (result.get(term, 0) + x * y) & MASK
    else:
        result.update(left)
        for term, value in right.items():
            result[term] = (result.get(term, 0) + (-value if subtract else value)) & MASK
    return {term: value for term, value in result.items() if value}


def constant(value):
    return {(0, 0): value & MASK} if value & MASK else {}


def scalar(value):
    if isinstance(value, dict) and not value.keys() - {(0, 0)}:
        return value.get((0, 0), 0)
    return None


def recurrence(body, counter, accumulator, condition, facts, written):
    values = {
        register: constant(low)
        for register, (low, high) in facts.items()
        if low == high and register not in written
    }
    values[counter] = {(1, 0): 1}
    values[accumulator] = {(0, 1): 1}
    values[condition] = constant(1)

    def read(operand):
        kind, value = operand
        return values.get(value) if kind == "r" else constant(value)

    for instruction in body[:-1]:
        op, args = instruction.op, instruction.args
        if op in {"const", "mov"}:
            result = read(args[1])
        elif op in {"add", "sub", "mul"}:
            result = combine(read(args[1]), read(args[2]), op == "mul", op == "sub")
        elif op == "mac":
            result = combine(combine(read(args[1]), read(args[2]), True), read(args[3]))
        elif op == "addsh":
            result = combine(read(args[1]), combine(read(args[2]), constant(1 << args[3][1]), True))
        elif op == "shl" and scalar(read(args[2])) is not None:
            result = combine(read(args[1]), constant(1 << (scalar(read(args[2])) & 31)), True)
        elif op == "mod":
            numerator, divisor = read(args[1]), scalar(read(args[2]))
            if not isinstance(numerator, dict) or divisor is None or not 0 < divisor <= MAX:
                return None
            result = ("mod", numerator, divisor)
        else:
            return None
        values[args[0][1]] = result

    if values.get(counter) != {(1, 0): 1, (0, 0): 1}:
        return None
    result = values.get(accumulator)
    modulus = None
    if isinstance(result, tuple):
        _, result, modulus = result
    if not isinstance(result, dict) or result.get((0, 1)) != 1:
        return None
    polynomial = {term: coefficient for term, coefficient in result.items() if term != (0, 1)}
    if any(a for _, a in polynomial):
        return None
    return polynomial, modulus


def lower_summation(blocks, machine, next_line):
    """Return a rewritten preheader, or None when a proof condition fails."""
    if sum(map(len, blocks.values())) > 100_000:
        return None
    predecessors = {label: [] for label in blocks}
    written = {}
    registers = set()
    for label, block in blocks.items():
        for kind, target in block[-1].args:
            if kind == "l":
                predecessors[target].append(label)
        written[label] = Counter(
            ins.args[0][1] for ins in block if SIGS[ins.op].startswith("d")
        )
        registers.update(value for ins in block for kind, value in ins.args if kind == "r")
    facts_at_entry = entry_intervals(blocks)
    next_register = max(registers, default=-1) + 1
    if next_register + 32 > 999999:
        return None

    for head, header in blocks.items():
        if head == next(iter(blocks)) or len(header) != 2 or header[0].op != "lt" or header[1].op != "br":
            continue
        comparison, branch = header
        condition, index, bound = comparison.args
        if branch.args[0] != condition or index[0] != "r":
            continue
        body_label, exit_label = branch.args[1][1], branch.args[2][1]
        if (body_label in (head, exit_label, next(iter(blocks)))
                or predecessors[body_label] != [head]):
            continue
        body, exit_block = blocks[body_label], blocks[exit_label]
        if (body[-1].op != "jmp" or body[-1].args != [("l", head)]
                or len(predecessors[head]) != 2 or len(exit_block) != 1 or exit_block[0].op != "ret"):
            continue
        acc = exit_block[0].args[0]
        if acc[0] != "r" or len({condition, index, bound, acc}) != 4:
            continue
        preheader = next(label for label in predecessors[head] if label != body_label)
        if blocks[preheader][-1].op != "jmp":
            continue
        loop_writes = written[head] + written[body_label]
        if bound[0] == "r" and bound[1] in loop_writes:
            continue
        facts = facts_at_entry.get(preheader, {}).copy()
        for instruction in blocks[preheader][:-1]:
            update(facts, instruction.op, instruction.args)
        low, high = interval(facts, bound)
        if not (0 <= low <= high <= 255) or interval(facts, index) != (0, 0):
            continue
        proved = recurrence(body, index[1], acc[1], condition[1], facts, loop_writes)
        if proved is None:
            continue
        polynomial, modulus = proved
        if modulus is not None:
            initial_low, initial_high = interval(facts, acc)
            coefficients = {i: signed(c) for (i, _), c in polynomial.items()}
            increments = [sum(c * i ** power for power, c in coefficients.items()) for i in range(high)]
            if (initial_low < 0 or initial_high >= modulus or any(value < 0 for value in increments)
                    or initial_high + sum(increments) > MAX):
                continue

        emitted = []

        def emit(op, *sources):
            nonlocal next_line, next_register
            dest = ("r", next_register)
            next_register += 1
            emitted.append(Instr(op, [dest, *sources], next_line, ""))
            next_line += 1
            return dest

        sums = {0: bound}
        product = None
        if any(power for power, _ in polynomial):
            minus_one = emit("sub", bound, ("i", 1))
            product = emit("mul", bound, minus_one)
        inverse_division = machine["lat_alu"] + machine["lat_mul"] <= machine["lat_div"]
        if (1, 0) in polynomial or (3, 0) in polynomial or ((2, 0) in polynomial and inverse_division):
            sums[1] = emit("shr", product, ("i", 1))
        if (2, 0) in polynomial:
            if machine["fused_addsh"] and machine["lat_addsh"] <= 2 * machine["lat_alu"]:
                odd = emit("addsh", ("i", MASK), bound, ("k", 1))
            else:
                twice = emit("add", bound, bound)
                odd = emit("sub", twice, ("i", 1))
            numerator = emit("mul", sums[1] if inverse_division else product, odd)
            sums[2] = (emit("mul", numerator, ("i", INVERSE_THREE)) if inverse_division
                       else emit("div", numerator, ("i", 6)))
        if (3, 0) in polynomial:
            sums[3] = emit("mul", sums[1], sums[1])
        initial = interval(facts, acc)
        result = ("i", initial[0] & MASK) if initial[0] == initial[1] else acc
        for (power, _), coefficient in sorted(polynomial.items()):
            term = sums[power]
            if coefficient != 1:
                term = emit("mul", term, ("i", coefficient))
            result = term if result == ("i", 0) else emit("add", result, term)
        if modulus is not None:
            result = emit("mod", result, ("i", modulus))
        old_jump = blocks[preheader][-1]
        emitted.append(Instr("ret", [result], old_jump.line, old_jump.text))
        blocks[preheader][-1:] = emitted
        return preheader
    return None
