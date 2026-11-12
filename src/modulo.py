"""Defer a common positive modulus through bounded nonnegative checksum loops.

Untainted values are identical. Tainted values are congruent modulo M, and
all operations that can differ are proved nonnegative and free of signed wrap.
Only canonically reduced live-out values may be restored on the normal exit.
"""

from .kirlib import Instr, SIGS
from .ranges import MAX, UNKNOWN, entry_intervals, interval, result_interval, update
from .registers import register_reads


class Reject(Exception):
    pass


def bounds(op, args, facts):
    result = result_interval(facts, op, args)
    if result != UNKNOWN:
        return result
    values = [interval(facts, operand) for operand in args]
    if op == "mul" and all(low >= 0 for low, _ in values):
        low = values[0][0] * values[1][0]
        high = values[0][1] * values[1][1]
    elif op in {"mac", "addsh"} and all(low >= 0 for low, _ in values):
        a, b, c = values
        if op == "mac":
            low, high = a[0] * b[0] + c[0], a[1] * b[1] + c[1]
        elif c[0] == c[1] and c[0] <= 31:
            low, high = a[0] + (b[0] << c[0]), a[1] + (b[1] << c[0])
        else:
            return UNKNOWN
    elif op == "shl" and values[0][0] >= 0 and values[1][0] == values[1][1]:
        shift = values[1][0] & 31
        low, high = values[0][0] << shift, values[0][1] << shift
    elif op in {"or", "xor"} and all(low >= 0 for low, _ in values):
        low, high = 0, (1 << max(high for _, high in values).bit_length()) - 1
    else:
        return UNKNOWN
    return (low, high) if 0 <= low <= high <= MAX else UNKNOWN


def positive_bounds(op, args, facts):
    """Mathematical bounds, deliberately without 32-bit constant folding."""
    values = [interval(facts, operand) for operand in args]
    guarded = values[1:] if op == "select" else values
    if any(low < 0 for low, _ in guarded):
        return UNKNOWN
    if op == "select":
        values = values[1:]
        low, high = min(lo for lo, _ in values), max(hi for _, hi in values)
    elif op == "add":
        low, high = sum(lo for lo, _ in values), sum(hi for _, hi in values)
    elif op == "mul":
        a, b = values
        low, high = a[0] * b[0], a[1] * b[1]
    elif op == "mac":
        a, b, c = values
        low, high = a[0] * b[0] + c[0], a[1] * b[1] + c[1]
    elif op in {"shl", "addsh"}:
        shift = values[-1]
        if shift[0] != shift[1]:
            return UNKNOWN
        amount = shift[0] & 31
        if op == "shl":
            low, high = values[0][0] << amount, values[0][1] << amount
        else:
            a, b = values[:2]
            low, high = a[0] + (b[0] << amount), a[1] + (b[1] << amount)
    else:
        return UNKNOWN
    return (low, high) if 0 <= low <= high <= MAX else UNKNOWN


def defer_moduli(blocks, pure):
    """Return changed labels for one proved loop, or an empty set on rejection."""
    if sum(map(len, blocks.values())) > 2000:
        return set()
    predecessors = {label: [] for label in blocks}
    for label, block in blocks.items():
        for target in dict.fromkeys(value for kind, value in block[-1].args if kind == "l"):
            predecessors[target].append(label)
    incoming = entry_intervals(blocks)
    budget = 200_000
    for head, header in blocks.items():
        if (head == next(iter(blocks)) or len(header) != 2 or header[0].op != "lt"
                or header[1].op != "br" or header[1].args[0] != header[0].args[0]):
            continue
        condition, counter, bound = header[0].args
        body_label, exit_label = (arg[1] for arg in header[1].args[1:])
        if (counter[0] != "r" or condition == counter or condition == bound
                or body_label in (head, exit_label, next(iter(blocks)))
                or exit_label in (head, next(iter(blocks)))
                or predecessors[body_label] != [head] or predecessors[exit_label] != [head]):
            continue
        body = blocks[body_label]
        if (len(body) > 128 or body[-1].op != "jmp" or body[-1].args != [("l", head)]
                or len(predecessors[head]) != 2 or not any(ins.op == "mod" for ins in body)
                or any(ins.op not in pure | {"mod", "load"} for ins in body[:-1])):
            continue
        preheader = next(label for label in predecessors[head] if label != body_label)
        if preheader == exit_label or blocks[preheader][-1].op != "jmp":
            continue
        written = {ins.args[0][1] for ins in body[:-1]}
        if condition[1] in written or (bound[0] == "r" and bound[1] in written):
            continue
        facts = incoming.get(preheader, {}).copy()
        for ins in blocks[preheader][:-1]:
            update(facts, ins.op, ins.args)
        low, high = interval(facts, bound)
        if not 0 <= low <= high <= 1024 or high == 0 or interval(facts, counter) != (0, 0):
            continue
        observed = {register for label, block in blocks.items() if label not in (head, body_label)
                    for ins in block for register in register_reads(ins)} & written
        original, candidate = facts.copy(), facts.copy()
        tainted, restore = set(), set()
        exit_bounds = {}
        modulus = None
        try:
            for iteration in range(high):
                original[counter[1]] = candidate[counter[1]] = (iteration, iteration)
                original[condition[1]] = candidate[condition[1]] = (1, 1)
                tainted.discard(counter[1]); tainted.discard(condition[1])
                for ins in body[:-1]:
                    budget -= 1
                    if budget < 0:
                        raise Reject()
                    op, args = ins.op, ins.args
                    sources = args[1:]
                    affected = any(kind == "r" and value in tainted for kind, value in sources)
                    if op == "mod":
                        divisor = interval(original, sources[1])
                        if ((sources[1][0] == "r" and sources[1][1] in tainted)
                                or divisor[0] != divisor[1] or divisor[0] <= 0):
                            raise Reject()
                        if modulus is None:
                            modulus = divisor[0]
                        if modulus != divisor[0]:
                            raise Reject()
                        before = interval(original, sources[0])
                        raw = interval(candidate, sources[0])
                        if not (0 <= before[0] <= before[1] <= MAX and 0 <= raw[0] <= raw[1] <= MAX):
                            raise Reject()
                        reduced = before if before[1] < modulus else (0, modulus - 1)
                        # If the candidate is already canonical, congruence
                        # gives numerical equality; no restoration is needed.
                        result_original, result_candidate = reduced, raw
                        affected = raw[1] >= modulus
                    elif op == "load":
                        # A possibly trapping read stays at the same point/address. With
                        # no loop stores or volatile I/O, deferred register state is not
                        # observable if it traps before normal-exit normalization.
                        if affected:
                            raise Reject()
                        result_original = result_candidate = UNKNOWN
                    elif op in {"mov", "const"}:
                        result_original = interval(original, sources[0])
                        result_candidate = interval(candidate, sources[0])
                    else:
                        if affected:
                            if op not in {"add", "mul", "mac", "addsh", "shl", "select"}:
                                raise Reject()
                            guarded = sources
                            if op in {"shl", "addsh"} and sources[-1][0] == "r" and sources[-1][1] in tainted:
                                raise Reject()
                            if op == "select":
                                if sources[0][0] == "r" and sources[0][1] in tainted:
                                    raise Reject()
                                guarded = sources[1:]
                            if any(interval(state, source)[0] < 0 for state in (original, candidate) for source in guarded):
                                raise Reject()
                        evaluator = positive_bounds if affected else bounds
                        result_original = evaluator(op, sources, original)
                        result_candidate = evaluator(op, sources, candidate)
                        if affected and not all(0 <= lo <= hi <= MAX for lo, hi in (result_original, result_candidate)):
                            raise Reject()
                    destination = args[0][1]
                    original[destination], candidate[destination] = result_original, result_candidate
                    if affected:
                        tainted.add(destination)
                    else:
                        tainted.discard(destination)
                expected = (iteration + 1, iteration + 1)
                if (counter[1] in tainted or interval(original, counter) != expected
                        or interval(candidate, counter) != expected):
                    raise Reject()
                restore.update(observed & tainted)
                # A value tainted only on later iterations may be noncanonical on an
                # earlier exit. Aggregate every possible exit, not just tainted ones.
                for register in observed:
                    lo, hi = interval(original, ("r", register))
                    previous = exit_bounds.get(register, (lo, hi))
                    exit_bounds[register] = min(lo, previous[0]), max(hi, previous[1])
            if modulus is None:
                raise Reject()
            for register in restore:
                initial = interval(facts, ("r", register))
                if not all(0 <= lo <= hi < modulus for lo, hi in (initial, exit_bounds[register])):
                    raise Reject()
        except Reject:
            continue
        changed_body = []
        for ins in body:
            changed_body.append(Instr("mov", ins.args[:2], ins.line, ins.text) if ins.op == "mod" else ins)
        next_line = max(ins.line for block in blocks.values() for ins in block) + 1
        normalizers = [Instr("mod", [("r", register), ("r", register), ("i", modulus)], next_line + index, "")
                       for index, register in enumerate(sorted(restore))]
        blocks[body_label] = changed_body
        blocks[exit_label] = normalizers + blocks[exit_label]
        return {body_label, exit_label}
    return set()
