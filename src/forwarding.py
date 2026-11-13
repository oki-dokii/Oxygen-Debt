"""Must-available ordinary memory values across CFG edges and joins."""

from collections import deque

from .kirlib import MASK, SIGS, Instr
from .optimizer import render_canonical
from .registers import register_reads


def literal(value):
    return (), value & MASK


def variable(name):
    return ((name, 1),), 0


def dependencies(expression):
    return {name for name, _ in expression[0]}


def expression(operand, aliases):
    kind, value = operand
    return aliases.get(value, variable(value)) if kind == 'r' else literal(value)


def linear(left, right, scale=1):
    coefficients = dict(left[0])
    for name, value in right[0]:
        coefficients[name] = (coefficients.get(name, 0) + value * scale) & MASK
    coefficients = tuple(sorted((name, value) for name, value in coefficients.items() if value))
    if len(coefficients) > 4:
        return None
    return coefficients, (left[1] + scale * right[1]) & MASK


def evaluate(ins, aliases):
    values = [expression(arg, aliases) for arg in ins.args[1:]]
    if ins.op in {'const', 'mov'}:
        return values[0]
    if ins.op in {'add', 'sub'}:
        return linear(values[0], values[1], 1 if ins.op == 'add' else -1)
    if ins.op == 'shl' and not values[1][0]:
        return linear(literal(0), values[0], 1 << (values[1][1] & 31))
    if ins.op == 'mul':
        left, right = values
        if not left[0]:
            return linear(literal(0), right, left[1])
        if not right[0]:
            return linear(literal(0), left, right[1])
    if ins.op == 'addsh' and not values[2][0]:
        scaled = linear(literal(0), values[1], 1 << (values[2][1] & 31))
        return linear(values[0], scaled) if scaled is not None else None
    if ins.op == 'mac':
        left, right, extra = values
        if not left[0]:
            scaled = linear(literal(0), right, left[1])
        elif not right[0]:
            scaled = linear(literal(0), left, right[1])
        else:
            return None
        return linear(scaled, extra) if scaled is not None else None
    return None


def substitute(value, name, replacement):
    coefficients = dict(value[0])
    scale = coefficients.pop(name, 0)
    return linear((tuple(sorted(coefficients.items())), value[1]), replacement, scale)


def inverse_assignment(value, name):
    if value is None:
        return None
    coefficient = dict(value[0]).get(name, 0)
    if not coefficient & 1:
        return None
    rest = (tuple((r, c) for r, c in value[0] if r != name), value[1])
    difference = linear(variable(name), rest, -1)
    return linear(literal(0), difference, pow(coefficient, -1, MASK + 1)) if difference is not None else None


def meet(states):
    if not states:
        return {}, {}
    aliases, memory = states[0]
    aliases = aliases.copy()
    memory = memory.copy()
    for other_aliases, other_memory in states[1:]:
        aliases = {name: value for name, value in aliases.items() if other_aliases.get(name) == value}
        memory = {address: shared for address, holders in memory.items()
                  if (shared := holders & other_memory.get(address, frozenset()))}
    return aliases, memory


def transfer(block, state, budget, replacements=None):
    aliases, memory = (part.copy() for part in state)
    for ins in block:
        budget[0] -= 1 + len(aliases) + len(memory)
        if budget[0] < 0:
            return None
        address = expression(ins.args[1] if ins.op == 'load' else ins.args[0], aliases) \
            if ins.op in {'load', 'store'} else None
        holders = memory.get(address, frozenset()) if ins.op == 'load' else frozenset()
        computed = evaluate(ins, aliases) if SIGS[ins.op].startswith('d') else None
        copied = []
        if ins.op in {'mov', 'const'}:
            source = ('i', computed[1]) if computed is not None and not computed[0] else ins.args[1]
            copied = [addr for addr, values in memory.items() if source in values]
        if replacements is not None and holders:
            source = min(holders, key=lambda arg: (arg[0] != 'i', arg[1]))
            replacements[ins.line] = Instr('mov' if source[0] == 'r' else 'const',
                                           [ins.args[0], source], ins.line, ins.text)
        if SIGS[ins.op].startswith('d'):
            dest = ins.args[0][1]
            inverse = inverse_assignment(computed, dest)
            def rebase(value):
                if dest not in dependencies(value):
                    return value
                return substitute(value, dest, inverse) if inverse is not None else None
            aliases = {name: rebased for name, value in aliases.items()
                       if name != dest and (rebased := rebase(value)) is not None}
            memory = {rebased: remaining for addr, values in memory.items()
                      if (rebased := rebase(addr)) is not None
                      and (remaining := values - {('r', dest)})}
            # A load's address and any copied equations refer to pre-write values.
            if address is not None:
                address = rebase(address)
            copied = [rebased for addr in copied if (rebased := rebase(addr)) is not None]
            if computed is not None and dest not in dependencies(computed):
                aliases[dest] = computed
            for addr in copied:
                if dest not in dependencies(addr):
                    memory[addr] = memory.get(addr, frozenset()) | {('r', dest)}
        if ins.op == 'load':
            dest = ins.args[0][1]
            # A self-overwriting address denotes the OLD register value; it may
            # not be recorded as an equation on the current register after load.
            if address is not None and dest not in dependencies(address):
                memory[address] = memory.get(address, frozenset()) | {('r', dest)}
        elif ins.op == 'store':
            # Equal coefficients and unequal constants are disjoint modulo 2^32.
            # Anything else may alias. Keep every original store and its trap.
            memory = {addr: values for addr, values in memory.items()
                      if addr[0] == address[0] and addr[1] != address[1]}
            source = ins.args[1]
            value = expression(source, aliases)
            if not value[0]:
                source = ('i', value[1])
            memory[address] = frozenset((source,))
        # Volatile ports have separate state. Their operands/effects stay in
        # place; vload still invalidates its destination through the write rule.
        if len(aliases) > 128:
            aliases = dict(sorted(aliases.items())[:128])
        if len(memory) > 32:
            memory = dict(sorted(memory.items())[:32])
    # Lift addresses through current equalities before a join. One predecessor
    # may know i=1 and cache literal address 1, while another caches address i.
    # Both can then supply the same relational fact memory[i]=holder.
    lifted = {}
    for name, value in aliases.items():
        for addr, values in memory.items():
            budget[0] -= 1
            if budget[0] < 0:
                return None
            if addr[0] == value[0]:
                key = (((name, 1),), (addr[1] - value[1]) & MASK)
                lifted[key] = lifted.get(key, frozenset()) | values
    for addr, values in lifted.items():
        memory[addr] = memory.get(addr, frozenset()) | values
    if len(memory) > 32:
        memory = dict(sorted(memory.items(), key=lambda item: (
            item[0][1] != 0, len(item[0][0]), item[0]))[:32])
    return aliases, memory


def analyse(program, work_limit=400_000):
    if len(program.instrs) > 2048 or len(program.block_labels) > 128:
        return None
    starts = [program.labels[label] for label in program.block_labels]
    blocks = {label: program.instrs[start:end] for label, start, end in zip(
        program.block_labels, starts, starts[1:] + [len(program.instrs)])}
    predecessors = {label: [] for label in blocks}
    successors = {}
    for label, block in blocks.items():
        successors[label] = tuple(dict.fromkeys(v for k, v in block[-1].args if k == 'l'))
        for target in successors[label]:
            predecessors[target].append(label)
    # Empty states are sound even on unvisited back edges. Never assume a fact
    # from just the already-visited subset of a block's incoming edges.
    outgoing = {label: ({}, {}) for label in blocks}
    incoming = {}
    pending, queued = deque(blocks), set(blocks)
    budget = [work_limit]
    while pending:
        label = pending.popleft()
        queued.remove(label)
        state = meet([outgoing[parent] for parent in predecessors[label]]) \
            if label != program.block_labels[0] else ({}, {})
        budget[0] -= 1 + sum(len(part) for parent in predecessors[label] for part in outgoing[parent])
        incoming[label] = state
        result = transfer(blocks[label], state, budget)
        if result is None or budget[0] < 0:
            return None
        if result != outgoing[label]:
            outgoing[label] = result
            for target in successors[label]:
                if target not in queued:
                    pending.append(target)
                    queued.add(target)
    return blocks, incoming, outgoing, budget


def forward(program, work_limit=400_000):
    analysis = analyse(program, work_limit)
    if analysis is None:
        return None
    blocks, incoming, _, budget = analysis
    replacements = {}
    for label, block in blocks.items():
        if transfer(block, incoming[label], budget, replacements) is None:
            return None
    if not replacements:
        return None
    rewritten = {label: [replacements.get(ins.line, ins) for ins in block] for label, block in blocks.items()}
    return render_canonical(program, rewritten, program.block_labels, {})


def join_copies(program):
    """Materialize differing available holders into a fresh common name at joins."""
    analysis = analyse(program)
    if analysis is None:
        return None
    blocks, incoming, outgoing, _ = analysis
    predecessors = {label: [] for label in blocks}
    for label, block in blocks.items():
        for target in dict.fromkeys(v for k, v in block[-1].args if k == 'l'):
            predecessors[target].append(label)
    names = {v for ins in program.instrs for k, v in ins.args if k == 'r'} | set(program.params)
    fresh = 0
    while fresh in names:
        fresh += 1
    line = max(ins.line for ins in program.instrs) + 1
    additions = {}
    count = 0
    for label in program.block_labels[1:]:
        parents = predecessors[label]
        if not 2 <= len(parents) <= 4:
            continue
        addresses = set.intersection(*(set(outgoing[parent][1]) for parent in parents))
        for addr in sorted(addresses):
            if addr in incoming[label][1]:
                continue
            for parent in parents:
                source = min(outgoing[parent][1][addr], key=lambda arg: (arg[0] != 'i', arg[1]))
                additions.setdefault(parent, []).append(Instr('mov' if source[0] == 'r' else 'const',
                                                              [('r', fresh), source], line, ''))
                line += 1
            names.add(fresh)
            fresh += 1
            while fresh in names:
                fresh += 1
            count += 1
            if count == 4:
                break
        if count == 4:
            break
    if not additions:
        return None
    rewritten = {label: block[:-1] + additions.get(label, []) + block[-1:] for label, block in blocks.items()}
    return render_canonical(program, rewritten, program.block_labels, {})


def candidates(program):
    from .kirlib import parse_program
    from .peeling import candidates as peeled_candidates

    results = []
    direct = forward(program)
    if direct is not None:
        results.append(direct)
    joined = join_copies(program)
    if joined is not None:
        for peeled in peeled_candidates(parse_program(joined)):
            rewritten = forward(parse_program(peeled))
            if rewritten is not None:
                results.append(rewritten)
    return list(dict.fromkeys(results))
