"""Schedule bounded blocks while preserving register and effect dependencies."""

from copy import copy

from .kiln import LATKEY, compile_program, time_trace
from .kirlib import Program, SIGS
from .registers import register_reads

EFFECTS = {"load", "store", "div", "mod", "vload", "vstore", "trap"}
FIELDS = ("srcs", "dst", "touch", "opnames", "isterm", "ismem")


def scheduled_order(block, machine):
    work = block[:-1]
    if not 3 <= len(work) <= 32 or any(ins.op in {"vload", "vstore"} for ins in work):
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
            return earliest, -height[index], index

        index = min(available, key=priority)
        start = priority(index)[0]
        available.remove(index)
        instruction = work[index]
        if start > cycle:
            cycle, used, memory_used = start, 0, 0
        used += 1
        memory_used += instruction.op in {"load", "store"}
        if SIGS[instruction.op].startswith("d"):
            ready[instruction.args[0][1]] = cycle + latency[index]
        result.append(index)
        for after in successors[index]:
            pending[after] -= 1
            if not pending[after]:
                available.add(after)
    result.append(len(block) - 1)
    return result if result != list(range(len(block))) else None


def schedule_blocks(blocks, order, params, machine):
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
    # Short paths do not model the LRU state carried around larger spilling loops.
    if model.nregs > machine["registers"] and machine["reg_spill_penalty"]:
        return False
    changed = False
    for label in order:
        permutation = scheduled_order(blocks[label], machine)
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
