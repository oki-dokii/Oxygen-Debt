"""Hoist pure arithmetic from loops with a header, body, and existing preheader."""

from collections import Counter

from .kirlib import SIGS
from .registers import register_reads


def hoist_loops(blocks, pure):
    predecessors = {label: [] for label in blocks}
    for label, block in blocks.items():
        for target in dict.fromkeys(value for kind, value in block[-1].args if kind == "l"):
            predecessors[target].append(label)

    entry = next(iter(blocks))
    loops = []
    for head, header in blocks.items():
        branch = header[-1]
        if head == entry or branch.op != "br" or len(predecessors[head]) != 2:
            continue
        for _, body in branch.args[1:]:
            if body in (entry, head) or predecessors[body] != [head]:
                continue
            back = blocks[body][-1]
            if back.op != "jmp" or back.args[0][1] != head:
                continue
            preheader = next(label for label in predecessors[head] if label != body)
            if blocks[preheader][-1].op == "jmp":
                loops.append((preheader, head, body))
    if not loops:
        return {}

    first_read = {}
    for label, block in blocks.items():
        for index, instruction in enumerate(block):
            for register in register_reads(instruction):
                owner, _ = first_read.setdefault(register, (label, index))
                if owner != label:
                    first_read[register] = (None, 0)

    placement = {}
    for preheader, head, body in loops:
        loop_writes = Counter(
            instruction.args[0][1]
            for label in (head, body) for instruction in blocks[label]
            if SIGS[instruction.op].startswith("d")
        )
        moved = []
        invariant = set()
        for index, instruction in enumerate(blocks[body]):
            if instruction.op not in pure:
                continue
            dest = instruction.args[0][1]
            owner, first = first_read.get(dest, (None, 0))
            # A skipped iteration may now write dest, so only move body-local definitions.
            if loop_writes[dest] != 1 or owner != body or first <= index:
                continue
            if all(register not in loop_writes or register in invariant
                   for register in register_reads(instruction)):
                invariant.add(dest)
                moved.append(instruction)
        if len(moved) < 2:
            continue

        moved_lines = {instruction.line for instruction in moved}
        retained = [instruction for instruction in blocks[body] if instruction.line not in moved_lines]
        exported = set()
        for instruction in retained:
            if instruction.op in pure and instruction.args[0][1] not in first_read:
                continue  # Liveness will remove this unused definition and its reads.
            exported.update(invariant.intersection(register_reads(instruction)))
        # Trade several repeated operations for a single extra value carried through the loop.
        if len(exported) != 1:
            continue
        anchor = blocks[preheader][-1].line
        for instruction in moved:
            placement[instruction.line] = anchor
        blocks[preheader][-1:-1] = moved
        blocks[body] = retained
    return placement
