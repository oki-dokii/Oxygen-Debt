"""Hoist pure invariants through natural loop nests with dominance checks."""

from collections import Counter

from .kirlib import SIGS
from .registers import register_reads


def hoist_nested(blocks, pure):
    if len(blocks) > 256 or sum(map(len, blocks.values())) > 2000:
        return {}
    labels = list(blocks)
    predecessors = {label: set() for label in labels}
    for label, block in blocks.items():
        for kind, target in block[-1].args:
            if kind == "l": predecessors[target].add(label)
    all_labels = set(labels)
    dominators = {label: ({label} if label == labels[0] else all_labels.copy()) for label in labels}
    for _ in range(256):
        changed = False
        for label in labels[1:]:
            parents = predecessors[label]
            common = set.intersection(*(dominators[parent] for parent in parents)) if parents else set()
            current = common | {label}
            if current != dominators[label]: dominators[label] = current; changed = True
        if not changed: break
    else:
        return {}
    loops = {}
    for latch, block in blocks.items():
        for kind, head in block[-1].args:
            if kind != "l" or head not in dominators[latch]: continue
            members = {head}; pending = [latch]
            while pending:
                node = pending.pop()
                if node in members: continue
                members.add(node); pending.extend(predecessors[node] - members)
            loops.setdefault(head, set()).update(members)
    placement = {}
    for head, members in sorted(loops.items(), key=lambda item: (-len(item[1]), labels.index(item[0]))):
        outside = predecessors[head] - members
        if head == labels[0] or len(outside) != 1: continue
        preheader = next(iter(outside))
        if blocks[preheader][-1].op != "jmp" or blocks[preheader][-1].args != [("l", head)]: continue
        writes = Counter(ins.args[0][1] for label in members for ins in blocks[label] if SIGS[ins.op].startswith("d"))
        uses = {}
        for label, block in blocks.items():
            for index, ins in enumerate(block):
                for register in register_reads(ins): uses.setdefault(register, []).append((label,index))
        moved, invariant = [], set()
        for label in sorted(members, key=lambda label: (len(dominators[label]), labels.index(label))):
            for index, ins in enumerate(blocks[label]):
                if ins.op not in pure: continue
                dest = ins.args[0][1]
                if writes[dest] != 1 or not uses.get(dest): continue
                if any(owner not in members or label not in dominators[owner]
                       or (owner == label and position <= index) for owner,position in uses[dest]): continue
                if any(r in writes and r not in invariant for r in register_reads(ins)): continue
                moved.append(ins); invariant.add(dest)
                if len(moved) == 16: break
            if len(moved) == 16: break
        if not moved: continue
        lines = {ins.line for ins in moved}
        for label in members: blocks[label] = [ins for ins in blocks[label] if ins.line not in lines]
        anchor = blocks[preheader][-1].line
        for ins in moved: placement[ins.line] = anchor
        blocks[preheader][-1:-1] = moved
    return placement
