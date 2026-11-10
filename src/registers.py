"""Reuse register names for values whose lifetimes stay within a block."""

from collections import OrderedDict
from heapq import heappop, heappush

from .kirlib import Instr, SIGS


def register_reads(instruction):
    sources = instruction.args[1:] if SIGS[instruction.op].startswith("d") else instruction.args
    return tuple(value for kind, value in sources if kind == "r")


def register_names(instructions):
    return {value for instruction in instructions for kind, value in instruction.args if kind == "r"}


def compact_block(block, pinned, pool):
    last_reads = {}
    ends = {}
    for index in reversed(range(len(block))):
        instruction = block[index]
        if SIGS[instruction.op].startswith("d"):
            register = instruction.args[0][1]
            if register not in pinned:
                ends[index] = last_reads.pop(register, index)
        for register in register_reads(instruction):
            if register not in pinned:
                last_reads.setdefault(register, index)
    if last_reads:
        return block

    available = []
    next_slot = 0
    active = {}
    release = {}
    result = []
    for index, instruction in enumerate(block):
        defines = SIGS[instruction.op].startswith("d")
        args = [
            (kind, pool[active[value]]) if kind == "r" and value not in pinned else (kind, value)
            for kind, value in instruction.args[int(defines):]
        ]
        # KIR reads its operands before writing its result, so a source can die here.
        for register in release.pop(index, ()):
            heappush(available, active.pop(register))
        if defines:
            dest = instruction.args[0]
            if index in ends:
                if available:
                    slot = heappop(available)
                else:
                    slot = next_slot
                    next_slot += 1
                if ends[index] == index:
                    heappush(available, slot)
                else:
                    active[dest[1]] = slot
                    release.setdefault(ends[index], []).append(dest[1])
                dest = ("r", pool[slot])
            args.insert(0, dest)
        result.append(Instr(instruction.op, args, instruction.line, instruction.text)
                      if args != instruction.args else instruction)
    return result


def reloads(blocks, capacity):
    resident = OrderedDict()
    spilled = set()
    count = 0
    for block in blocks:
        for instruction in block:
            touched = register_reads(instruction)
            if SIGS[instruction.op].startswith("d"):
                touched += (instruction.args[0][1],)
            for register in dict.fromkeys(touched):
                if register in resident:
                    resident.move_to_end(register)
                else:
                    if register in spilled:
                        count += 1
                        spilled.remove(register)
                    if len(resident) == capacity:
                        spilled.add(resident.popitem(last=False)[0])
                    resident[register] = None
    return count


def compact_registers(blocks, edits, live_in, params, machine):
    capacity = machine["registers"]
    pinned = set(params)
    for live in live_in.values():
        pinned.update(live)
    registers = set(params)
    retained = {}
    for label, block in blocks.items():
        retained[label] = [
            current for instruction in block
            if (current := edits.get(instruction.line, instruction)) is not None
        ]
        registers.update(register_names(retained[label]))
        pinned.update(register_names(ins for ins in retained[label] if ins.op in {"vload", "vstore"}))

    if len(registers) <= capacity:
        return
    pool = sorted(registers - pinned)
    if len(pool) < 2:
        return
    candidate = {label: compact_block(block, pinned, pool) for label, block in retained.items()}
    if len(register_names(ins for block in candidate.values() for ins in block) | set(params)) > capacity:
        # Sharing a name can make it return from a spill more often on a back edge.
        # Check short cycles when the new program still exceeds hardware capacity.
        successors = {
            label: tuple(dict.fromkeys(value for kind, value in block[-1].args if kind == "l"))
            for label, block in retained.items()
        }
        for origin, targets in successors.items():
            for target in targets:
                if origin not in successors[target]:
                    continue
                labels = (origin,) if origin == target else (origin, target)
                before = reloads((retained[label] for label in labels * 3), capacity)
                after = reloads((candidate[label] for label in labels * 3), capacity)
                if after > before:
                    for label in labels:
                        candidate[label] = retained[label]
    for label, block in retained.items():
        for before, after in zip(block, candidate[label]):
            if before is not after:
                edits[before.line] = after
