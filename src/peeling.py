"""Distinguish a natural loop's first iteration by bounded CFG copying."""

from .kirlib import Instr
from .optimizer import render_canonical


def candidates(program):
    if len(program.instrs) > 1024 or len(program.block_labels) > 64:
        return []
    labels = program.block_labels
    starts = [program.labels[label] for label in labels]
    blocks = {label: program.instrs[start:end] for label, start, end in zip(
        labels, starts, starts[1:] + [len(program.instrs)])}
    predecessors = {label: set() for label in labels}
    successors = {}
    for label, block in blocks.items():
        successors[label] = {v for k, v in block[-1].args if k == 'l'}
        for target in successors[label]:
            predecessors[target].add(label)
    dominators = {label: {label} if label == labels[0] else set(labels) for label in labels}
    for _ in range(64):
        changed = False
        for label in labels[1:]:
            common = set.intersection(*(dominators[p] for p in predecessors[label])) if predecessors[label] else set()
            result = common | {label}
            if result != dominators[label]:
                dominators[label] = result
                changed = True
        if not changed:
            break
    else:
        return []
    loops = {}
    for latch in labels:
        for head in successors[latch] & dominators[latch]:
            members, pending = {head}, [latch]
            while pending:
                label = pending.pop()
                if label not in members:
                    members.add(label)
                    pending.extend(predecessors[label] - members)
            loops.setdefault(head, set()).update(members)
    results = []
    for head, members in sorted(loops.items(), key=lambda item: (len(item[1]), labels.index(item[0]))):
        if (head == labels[0] or len(members) > 12 or sum(len(blocks[l]) for l in members) > 128
                or len(predecessors[head] - members) != 1
                or any(predecessors[label] - members for label in members - {head})
                or not any(ins.op == 'load' for label in members for ins in blocks[label])):
            continue
        # Only innermost regions: removing header back edges must leave a DAG.
        pending = [head]
        visited = set()
        while pending:
            label = pending.pop()
            if label in visited:
                continue
            visited.add(label)
            for target in successors[label] & members - {head}:
                if predecessors[target] & members <= visited:
                    pending.append(target)
        if members - visited:
            continue
        copies = {}
        for index, label in enumerate(l for l in labels if l in members):
            fresh = f'peeled_{len(results)}_{index}'
            while fresh in blocks or fresh in copies.values():
                fresh += '_'
            copies[label] = fresh
        rewritten = {label: block[:] for label, block in blocks.items()}
        line = max(ins.line for ins in program.instrs) + 1
        for label in labels:
            if label not in members:
                continue
            original = rewritten[label][-1]
            args = [(k, copies[head] if k == 'l' and v == head else v) for k, v in original.args]
            rewritten[label][-1] = Instr(original.op, args, original.line, original.text)
            rewritten[copies[label]] = []
            for ins in blocks[label]:
                args = [(k, copies.get(v, v) if k == 'l' else v) for k, v in ins.args]
                rewritten[copies[label]].append(Instr(ins.op, args, line, ''))
                line += 1
        results.append(render_canonical(program, rewritten, list(rewritten), {}))
        if len(results) == 2:
            break
    return results
