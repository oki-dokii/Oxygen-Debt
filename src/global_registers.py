"""Bounded whole-register colouring of mutable KIR, without changing control flow."""

from collections import Counter, deque

from .kirlib import Instr, SIGS
from .registers import register_names, register_reads


def interference(blocks, params, budget=500_000):
    """Return complete interference or None; incomplete liveness never authorizes reuse."""
    names = register_names(ins for block in blocks.values() for ins in block) | set(params)
    if len(names) > 256 or len(blocks) > 128 or sum(map(len, blocks.values())) > 2048:
        return None
    successors = {label: tuple(dict.fromkeys(value for kind, value in block[-1].args if kind == 'l'))
                  for label, block in blocks.items()}
    predecessors = {label: [] for label in blocks}
    uses, definitions = {}, {}
    for label, block in blocks.items():
        used, defined = set(), set()
        for ins in block:
            used.update(set(register_reads(ins)) - defined)
            if SIGS[ins.op].startswith('d'):
                defined.add(ins.args[0][1])
        uses[label], definitions[label] = used, defined
        for target in successors[label]:
            predecessors[target].append(label)
    live_in = {label: set() for label in blocks}
    pending, queued = deque(reversed(blocks)), set(blocks)
    while pending:
        label = pending.popleft()
        queued.remove(label)
        live = set().union(*(live_in[target] for target in successors[label]))
        budget -= len(live) + len(uses[label]) + len(predecessors[label]) + 1
        if budget < 0:
            return None
        live = uses[label] | (live - definitions[label])
        if live != live_in[label]:
            live_in[label] = live
            for before in predecessors[label]:
                if before not in queued:
                    queued.add(before)
                    pending.append(before)
    edges = {name: set() for name in names}
    affinities = {name: Counter() for name in names}
    touches = Counter()

    def connect(name, others):
        for other in others:
            if other != name:
                edges[name].add(other)
                edges[other].add(name)

    # Undefined non-parameters start at zero. Distinct live initial values must
    # remain distinct, including parameter bindings even when a parameter is dead.
    entry = live_in[next(iter(blocks))] | set(params)
    for name in entry:
        connect(name, entry)
    for label, block in blocks.items():
        live = set().union(*(live_in[target] for target in successors[label]))
        for ins in reversed(block):
            reads = register_reads(ins)
            touches.update(reads)
            if SIGS[ins.op].startswith('d'):
                dest = ins.args[0][1]
                touches[dest] += 1
                budget -= len(live) + 1
                if budget < 0:
                    return None
                # Include dead writes: they must not clobber another live value.
                connect(dest, live)
                live.discard(dest)
                if ins.op == 'mov' and reads:
                    affinities[dest][reads[0]] += 1
                    affinities[reads[0]][dest] += 1
            live.update(reads)
    return edges, affinities, touches


def colour(blocks, params, strategy='saturation'):
    analysis = interference(blocks, params)
    if analysis is None:
        return None
    edges, affinities, touches = analysis
    # Keep parameter names and their binding order fixed. All remaining palette
    # names start at zero, as required for entry-live non-parameter values.
    colours = {name: index for index, name in enumerate(params)}
    palette = list(params) + sorted(set(edges) - set(params))
    pending = set(edges) - set(params)
    while pending:
        if strategy == 'degree':
            name = min(pending, key=lambda n: (-len(edges[n]), -touches[n], n))
        else:
            name = min(pending, key=lambda n: (
                -len({colours[v] for v in edges[n] if v in colours}), -len(edges[n]), -touches[n], n))
        forbidden = {colours[other] for other in edges[name] if other in colours}
        # Never reuse parameter names: this also preserves implicit initial zeros.
        forbidden.update(range(len(params)))
        preferred = [colours[other] for other in sorted(affinities[name],
                     key=lambda n: (-affinities[name][n], n)) if other in colours]
        chosen = next((c for c in preferred if c not in forbidden), None)
        if chosen is None:
            chosen = next(c for c in range(len(palette)) if c not in forbidden)
        colours[name] = chosen
        pending.remove(name)
    mapping = {name: palette[index] for name, index in colours.items()}
    if all(name == replacement for name, replacement in mapping.items()):
        return None
    return {label: [Instr(ins.op, [(kind, mapping[value]) if kind == 'r' else (kind, value)
                                 for kind, value in ins.args], ins.line, ins.text)
                    for ins in block] for label, block in blocks.items()}


def split_lifetimes(blocks, params, budget=500_000):
    """Separate def-use webs with reaching definitions; no phi/copy insertion."""
    names = sorted(register_names(ins for block in blocks.values() for ins in block) | set(params))
    if len(names) > 128 or len(blocks) > 128 or sum(map(len, blocks.values())) > 1024:
        return None
    successors = {label: tuple(dict.fromkeys(v for k, v in block[-1].args if k == 'l'))
                  for label, block in blocks.items()}
    entry = next(iter(blocks))
    reachable, pending = set(), [entry]
    while pending:
        label = pending.pop()
        if label not in reachable:
            reachable.add(label)
            pending.extend(successors[label])
    if reachable != set(blocks):
        return None
    initial = {name: 1 << index for index, name in enumerate(names)}
    definitions, last = {}, {}
    nodes = len(names)
    for label, block in blocks.items():
        last[label] = {}
        for index, ins in enumerate(block):
            if SIGS[ins.op].startswith('d'):
                definitions[label, index] = 1 << nodes
                last[label][ins.args[0][1]] = 1 << nodes
                nodes += 1
    incoming = {label: {} for label in blocks}
    incoming[entry] = initial.copy()
    pending, queued = deque([entry]), {entry}
    while pending:
        label = pending.popleft()
        queued.remove(label)
        outgoing = incoming[label] | last[label]
        for target in successors[label]:
            changed = False
            for name, values in outgoing.items():
                budget -= 1
                if budget < 0:
                    return None
                merged = incoming[target].get(name, 0) | values
                if merged != incoming[target].get(name, 0):
                    incoming[target][name] = merged
                    changed = True
            if changed and target not in queued:
                pending.append(target)
                queued.add(target)
    parent = list(range(nodes))

    def root(index):
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def members(bits):
        while bits:
            bit = bits & -bits
            yield bit.bit_length() - 1
            bits -= bit

    def join(bits):
        nonlocal budget
        values = list(members(bits))
        if not values:
            raise ValueError('missing reaching definition')
        first = root(values[0])
        for index in values[1:]:
            budget -= 1
            other = root(index)
            if first != other:
                low, high = sorted((first, other))
                parent[high] = low
                first = low
        return values[0]

    reads = {}
    for label, block in blocks.items():
        state = incoming[label].copy()
        for index, ins in enumerate(block):
            for name in register_reads(ins):
                reads[label, index, name] = join(state[name])
            if SIGS[ins.op].startswith('d'):
                state[ins.args[0][1]] = definitions[label, index]
            if budget < 0:
                return None
    # An initial root keeps its original zero or parameter binding. Other webs
    # get fresh zero-initialized names. Every read joins ALL reaching definitions,
    # so a join/loop never needs an inserted transfer or a guessed incoming value.
    mapping = {root(index): name for index, name in enumerate(names)}
    next_name = max(names, default=-1) + 1
    for index in range(nodes):
        key = root(index)
        if key not in mapping:
            mapping[key] = next_name
            next_name += 1
    if len(mapping) > 256:
        return None
    result = {}
    for label, block in blocks.items():
        result[label] = []
        for index, ins in enumerate(block):
            args = []
            for pos, (kind, value) in enumerate(ins.args):
                if kind == 'r':
                    node = (definitions[label, index].bit_length() - 1
                            if pos == 0 and SIGS[ins.op].startswith('d') else reads[label, index, value])
                    value = mapping[root(node)]
                args.append((kind, value))
            result[label].append(Instr(ins.op, args, ins.line, ins.text))
    return result
