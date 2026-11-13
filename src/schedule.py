"""Schedule bounded blocks while preserving register and effect dependencies."""

from collections import Counter
from copy import copy

from .kiln import LATKEY, compile_program, time_trace
from .kirlib import Program, SIGS
from .registers import register_reads

EFFECTS = {"load", "store", "div", "mod", "vload", "vstore", "trap"}
FIELDS = ("srcs", "dst", "touch", "opnames", "isterm", "ismem")


def spill_contexts(label, predecessors, successors, indices):
    """Bound all short incoming/outgoing contexts and simple cycles through a block."""
    def walks(edges, backward=False):
        pending = [(label,)]
        finished = []
        while pending:
            path = pending.pop(0)
            neighbors = edges[path[0] if backward else path[-1]]
            if len(path) == 4 or not neighbors:
                finished.append(path)
            else:
                pending.extend((neighbor, *path) if backward else (*path, neighbor)
                               for neighbor in neighbors)
            if len(pending) + len(finished) > 8:
                return None
        return finished

    incoming, outgoing = walks(predecessors, True), walks(successors)
    if incoming is None or outgoing is None:
        return None
    paths = [before[:-1] + after for before in incoming for after in outgoing]
    pending = [(label,)]
    cycles = []
    visits = 0
    while pending:
        path = pending.pop()
        visits += 1
        if visits > 256 or len(cycles) > 8:
            return None
        for target in successors[path[-1]]:
            if target == label:
                cycles.append(path)
                if len(cycles) > 8:
                    return None
            elif target not in path and len(path) < 6:
                pending.append((*path, target))
    for cycle in cycles:
        paths.extend(before[:-1] + cycle * 3 + after
                     for before in incoming for after in outgoing)
        if len(paths) > 128:
            return None
    paths = list(dict.fromkeys(paths))
    if any(sum(len(indices[block]) for block in path) > 512 for path in paths):
        return None
    return paths


def scheduled_order(block, machine, mode="latency"):
    work = block[:-1]
    if not 3 <= len(work) <= (32 if mode == "latency" else 64) or any(ins.op in {"vload", "vstore"} for ins in work):
        return None
    predecessors = [set() for _ in work]
    successors = [set() for _ in work]
    writers = {}
    readers = {}
    last_effect = None
    for index, instruction in enumerate(work):
        sources = register_reads(instruction)
        for register in sources:
            if register in writers:
                predecessors[index].add(writers[register])
        if SIGS[instruction.op].startswith("d"):
            register = instruction.args[0][1]
            if register in writers:
                predecessors[index].add(writers[register])
            predecessors[index].update(readers.pop(register, ()))
            writers[register] = index
        for register in sources:
            readers.setdefault(register, set()).add(index)
        if instruction.op in EFFECTS:
            if last_effect is not None:
                predecessors[index].add(last_effect)
            last_effect = index
        predecessors[index].discard(index)
        for before in predecessors[index]:
            successors[before].add(index)
    latency = [machine[LATKEY[ins.op]] if ins.op in LATKEY else 1 for ins in work]
    height = [0] * len(work)
    for index in reversed(range(len(work))):
        height[index] = latency[index] + max((height[n] for n in successors[index]), default=0)
    # Track value versions for pressure estimates; mutable register names alone
    # would conflate values on opposite sides of an overwrite. This is a heuristic
    # only: the dependency DAG, not this estimate, authorizes each permutation.
    versions, inputs, outputs = {}, [], []
    for index, instruction in enumerate(block):
        inputs.append(set(versions.get(r, (r, -1)) for r in register_reads(instruction)))
        dest = instruction.args[0][1] if SIGS[instruction.op].startswith("d") else None
        outputs.append((dest, index) if dest is not None else None)
        if dest is not None:
            versions[dest] = outputs[-1]
    remaining = Counter(value for values in inputs for value in values)
    # Keep final definitions live conservatively, including values used by successors.
    remaining.update(versions.values())
    active = {value for value in remaining if value[1] == -1}
    pending = [len(before) for before in predecessors]
    available = {index for index, count in enumerate(pending) if not count}
    ready = {}
    cycle = used = memory_used = 0
    result = []
    while available:
        def priority(index):
            instruction = work[index]
            names = register_reads(instruction)
            if SIGS[instruction.op].startswith("d"):
                names += (instruction.args[0][1],)
            earliest = max(cycle, max((ready.get(r, 0) for r in names), default=0))
            memory = instruction.op in {"load", "store"}
            if earliest == cycle and (used >= machine["issue_width"]
                                      or (memory and memory_used >= machine["mem_ports"])):
                earliest += 1
            if mode != "latency":
                delta = int(outputs[index] is not None and remaining[outputs[index]] > 0)
                delta -= sum(remaining[value] == 1 for value in inputs[index])
                if mode == "pressure_first":
                    return max(0, len(active) + delta - machine["registers"]), earliest, delta, -height[index], index
                return earliest, delta, -height[index], index
            return earliest, -height[index], index

        index = min(available, key=priority)
        start = priority(index)[1 if mode == "pressure_first" else 0]
        available.remove(index)
        instruction = work[index]
        if start > cycle:
            cycle, used, memory_used = start, 0, 0
        used += 1
        memory_used += instruction.op in {"load", "store"}
        if SIGS[instruction.op].startswith("d"):
            ready[instruction.args[0][1]] = cycle + latency[index]
        result.append(index)
        for value in inputs[index]:
            remaining[value] -= 1
            if not remaining[value]:
                active.discard(value)
        if outputs[index] is not None and remaining[outputs[index]]:
            active.add(outputs[index])
        for after in successors[index]:
            pending[after] -= 1
            if not pending[after]:
                available.add(after)
    result.append(len(block) - 1)
    return result if result != list(range(len(block))) else None


def schedule_blocks(blocks, order, params, machine, mode="latency"):
    if sum(map(len, blocks.values())) > 5000:
        return False
    program = Program()
    program.name = "schedule_model"
    program.params = list(params)
    indices = {}
    successors = {}
    predecessors = {label: [] for label in blocks}
    for label in order:
        program.labels[label] = len(program.instrs)
        program.block_labels.append(label)
        indices[label] = list(range(len(program.instrs), len(program.instrs) + len(blocks[label])))
        program.instrs.extend(blocks[label])
        program.block_of.extend([label] * len(blocks[label]))
        successors[label] = tuple(dict.fromkeys(value for kind, value in blocks[label][-1].args if kind == "l"))
        for target in successors[label]:
            predecessors[target].append(label)
    model = compile_program(program)
    spilling = model.nregs > machine["registers"] and machine["reg_spill_penalty"]
    budget = 200_000
    changed = False
    for label in order:
        permutation = scheduled_order(blocks[label], machine, mode)
        if permutation is None:
            continue
        candidate = copy(model)
        positions = indices[label]
        for field in FIELDS:
            values = getattr(model, field)
            replacement = values.copy()
            for dest, source in zip(positions, permutation):
                replacement[dest] = values[positions[source]]
            setattr(candidate, field, replacement)
        paths = [(label,) * 3]
        for before in predecessors[label]:
            paths.append((before, label))
            if before in successors[label]:
                paths.append((before, label) * 3)
        for after in successors[label]:
            paths.append((label, after))
        if spilling:
            contexts = spill_contexts(label, predecessors, successors, indices)
            if contexts is None:
                continue
            paths.extend(contexts)
            work = 2 * sum(len(model.opnames) + sum(len(indices[b]) for b in path) for path in paths)
            if work > budget:
                continue
            budget -= work
        faster = False
        for path in paths:
            trace = [pc for block in path for pc in indices[block]]
            old_time, new_time = (time_trace(cp, trace, machine) for cp in (model, candidate))
            if new_time > old_time:
                break
            faster |= new_time < old_time
        else:
            if faster:
                blocks[label] = [blocks[label][index] for index in permutation]
                model = candidate
                changed = True
    return changed
