"""Simplify conditional assignments and adjacent straight-line blocks."""

from collections import Counter

from .kirlib import Instr


def select_assignments(blocks, edits):
    incoming = Counter(
        target for block in blocks.values() for kind, target in block[-1].args if kind == "l"
    )
    entry = next(iter(blocks))
    placement = {}
    for block in blocks.values():
        branch = block[-1]
        if branch.op != "br":
            continue
        condition, yes, no = branch.args
        if yes == no or entry in (yes[1], no[1]):
            continue
        if incoming[yes[1]] != 1 or incoming[no[1]] != 1:
            continue
        left, right = blocks[yes[1]], blocks[no[1]]
        if (len(left) != 2 or len(right) != 2
                or left[0].op not in {"const", "mov"} or right[0].op not in {"const", "mov"}
                or left[0].args[0] != right[0].args[0]
                or left[-1].op != "jmp" or right[-1].op != "jmp"
                or left[-1].args != right[-1].args):
            continue
        first, second = left[0], right[0]
        args = [first.args[0], condition, first.args[1], second.args[1]]
        selected = Instr("select", args, first.line, first.text)
        jump = Instr("jmp", left[-1].args, branch.line, branch.text)
        edits[first.line] = selected
        edits[branch.line] = jump
        placement[first.line] = branch.line
        left.pop(0)
        block[-1:] = [selected, jump]
    return placement


def merge_straight_lines(blocks, edits, label_lines, order):
    """Join adjacent blocks when the second has exactly one incoming edge."""
    incoming = Counter(
        target for block in blocks.values() for kind, target in block[-1].args if kind == "l"
    )
    changed = False
    following = dict(zip(order, order[1:]))
    previous = None
    for label in tuple(blocks):
        if previous is not None:
            before = blocks[previous]
            jump = before[-1]
            if (incoming[label] == 1 and following.get(previous) == label
                    and jump.op == "jmp" and jump.args == [("l", label)]):
                edits[jump.line] = None
                edits[label_lines[label]] = None
                before.pop()
                before.extend(blocks.pop(label))
                following[previous] = following.get(label)
                changed = True
                continue
        previous = label
    return changed
