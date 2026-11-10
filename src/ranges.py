"""Conservative signed intervals for arithmetic and comparison edges."""

from collections import deque

from .kirlib import MASK, SIGS

MIN, MAX = -(1 << 31), (1 << 31) - 1
UNKNOWN = (MIN, MAX)
RANGE_BUDGET = 500_000


def signed(word):
    return word if word <= MAX else word - (MASK + 1)


def interval(facts, operand):
    kind, value = operand
    if kind == "r":
        return facts.get(value, UNKNOWN)
    number = signed(value)
    return number, number


def record(facts, operand, bounds):
    if operand[0] == "r":
        if bounds == UNKNOWN:
            facts.pop(operand[1], None)
        else:
            facts[operand[1]] = bounds


def result_interval(facts, op, sources):
    if op in {"const", "mov"}:
        return interval(facts, sources[0])
    if op in {"lt", "eq"}:
        return 0, 1
    if op == "select":
        yes, no = (interval(facts, source) for source in sources[1:])
        return min(yes[0], no[0]), max(yes[1], no[1])
    if op in {"add", "sub", "and", "shr"}:
        left, right = (interval(facts, source) for source in sources)
        if op == "and":
            masks = [lo for lo, hi in (left, right) if lo == hi and lo >= 0]
            return (0, min(masks)) if masks else UNKNOWN
        if op == "shr":
            shift = right[0] & 31
            if right[0] == right[1] and shift:
                return 0, MASK >> shift
            return UNKNOWN
        if op == "add":
            low, high = left[0] + right[0], left[1] + right[1]
        else:
            low, high = left[0] - right[1], left[1] - right[0]
        if MIN <= low <= high <= MAX:
            return low, high
    return UNKNOWN


def update(facts, op, args):
    if SIGS[op].startswith("d"):
        record(facts, args[0], result_interval(facts, op, args[1:]))


def comparison_edges(block, facts):
    branch = block[-1]
    if branch.op != "br" or len(block) < 2:
        return
    comparison = block[-2]
    if comparison.args[0] != branch.args[0]:
        return
    negation = None
    if comparison.op == "eq" and len(block) >= 3:
        candidate = block[-3]
        if candidate.op == "lt" and (
            comparison.args[1:] == [candidate.args[0], ("i", 0)]
            or comparison.args[1:] == [("i", 0), candidate.args[0]]
        ):
            negation, comparison = comparison.args[0], candidate
    if comparison.op != "lt":
        return
    dest, left, right = comparison.args
    if dest in (left, right) or negation in (left, right) or left == right:
        return
    a, b = interval(facts, left), interval(facts, right)
    true = (a[0], min(a[1], b[1] - 1)), (max(b[0], a[0] + 1), b[1])
    false = (max(a[0], b[0]), a[1]), (b[0], min(b[1], a[1]))
    return (left, right), (false, true) if negation is not None else (true, false)


def entry_intervals(blocks):
    entry = next(iter(blocks))
    incoming = {entry: {}}
    order = {entry: 0}
    updates = {}
    pending = deque([entry])
    queued = {entry}
    budget = RANGE_BUDGET
    while pending:
        label = pending.popleft()
        queued.remove(label)
        block = blocks[label]
        facts = incoming[label].copy()
        budget -= len(block) + len(facts)
        if budget < 0:
            return {}
        for instruction in block:
            update(facts, instruction.op, instruction.args)
        comparison = comparison_edges(block, facts)
        targets = (value for kind, value in block[-1].args if kind == "l")
        for index, target in enumerate(targets):
            outgoing = facts
            if comparison:
                operands, alternatives = comparison
                refined = alternatives[index]
                # Keeping impossible edges conservatively avoids needing a bottom state.
                if all(lo <= hi for lo, hi in refined):
                    outgoing = facts.copy()
                    for operand, bounds in zip(operands, refined):
                        record(outgoing, operand, bounds)
            previous = incoming.get(target)
            budget -= len(outgoing) + (len(previous) if previous is not None else 0) + 1
            if budget < 0:
                return {}
            if previous is None:
                joined = outgoing
                order[target] = len(order)
            else:
                joined = {}
                # Every cycle has an edge going back in discovery order.
                widen = order[target] <= order[label] and updates.get(target, 0) >= 2
                for register in previous.keys() & outgoing.keys():
                    lo, hi = previous[register]
                    next_lo, next_hi = outgoing[register]
                    lower = MIN if widen and next_lo < lo else min(lo, next_lo)
                    upper = MAX if widen and next_hi > hi else max(hi, next_hi)
                    if (lower, upper) != UNKNOWN:
                        joined[register] = lower, upper
            if joined != previous:
                incoming[target] = joined
                updates[target] = updates.get(target, 0) + 1
                if target not in queued:
                    pending.append(target)
                    queued.add(target)
    return incoming


def reduce_division(op, args, facts):
    dest, numerator, operand = args
    lo, hi = interval(facts, operand)
    if lo != hi or lo == 0:
        return None
    divisor = lo
    low, high = interval(facts, numerator)
    if low == high:
        quotient = abs(low) // abs(divisor)
        if (low < 0) != (divisor < 0):
            quotient = -quotient
        result = quotient if op == "div" else low - quotient * divisor
        return "const", [dest, ("i", result & MASK)]
    if abs(divisor) == 1:
        if op == "mod":
            return "const", [dest, ("i", 0)]
        if divisor == 1:
            return "mov", [dest, numerator]
        return "sub", [dest, ("i", 0), numerator]
    magnitude = abs(divisor)
    if -magnitude < low <= high < magnitude:
        return ("const", [dest, ("i", 0)]) if op == "div" else ("mov", [dest, numerator])
    if low >= 0 and (magnitude & (magnitude - 1)) == 0:
        if op == "mod":
            return "and", [dest, numerator, ("i", magnitude - 1)]
        if divisor > 0:
            return "shr", [dest, numerator, ("i", magnitude.bit_length() - 1)]
    if operand[0] == "r":
        return op, [dest, numerator, ("i", divisor & MASK)]
    return None
