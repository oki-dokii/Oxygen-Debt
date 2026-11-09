"""Choose a block order using optional branch counts."""

from .kirlib import read_text


def load_profile(path):
    if path is None:
        return {}
    try:
        source = read_text(path)
    except (OSError, UnicodeError):
        return {}

    counts = {}
    for line in source.splitlines():
        fields = line.partition("#")[0].split()
        if len(fields) != 4 or fields[0] != "edge" or not fields[3].isascii() or not fields[3].isdigit():
            continue
        _, origin, target, count = fields
        try:
            weight = int(count)
        except ValueError:
            continue
        if weight:
            edge = origin, target
            counts[edge] = counts.get(edge, 0) + weight
    return counts


def choose_layout(blocks, edits, machine, profile):
    """Return a reordered list of labels only if it lowers estimated cost."""
    if not profile or len(blocks) < 3 or not machine["taken_branch_penalty"]:
        return None
    original = list(blocks)
    entry = original[0]
    positions = {label: index for index, label in enumerate(original)}
    edges = {}
    incoming = dict.fromkeys(original, 0)
    outgoing = dict.fromkeys(original, 0)
    for origin, block in blocks.items():
        for kind, target in dict.fromkeys(block[-1].args):
            if kind != "l":
                continue
            weight = profile.get((origin, target), 0)
            if weight:
                edges[origin, target] = weight
                incoming[target] += weight
                outgoing[origin] += weight
    if not edges:
        return None

    # Prefer an existing fallthrough when the profile gives only a narrow lead
    # to another edge. Missing counts also carry uncertainty after CFG edits.
    for origin, target in zip(original, original[1:]):
        if ("l", target) in blocks[origin][-1].args:
            edges[origin, target] = edges.get((origin, target), 0) + max(1, outgoing[origin] // 4)

    following = {}
    preceding = set()
    parents = dict.fromkeys(original)

    def head(label):
        while parents[label] is not None:
            parent = parents[label]
            if parents[parent] is not None:
                parents[label] = parents[parent]
            label = parent
        return label

    def priority(edge):
        origin, target = edge
        i, j = positions[origin], positions[target]
        return -edges[edge], j != i + 1, i, j

    for origin, target in sorted(edges, key=priority):
        if origin in following or target in preceding or target == entry:
            continue
        origin_head = head(origin)
        if origin_head != head(target):
            parents[target] = origin_head
            following[origin] = target
            preceding.add(target)

    candidate = []
    for label in original:
        if label not in preceding:
            while label is not None:
                candidate.append(label)
                label = following.get(label)
    if candidate == original:
        return None

    visits = {label: max(incoming[label], outgoing[label]) for label in original}
    sizes = {
        label: sum(edits.get(instruction.line, instruction) is not None for instruction in block)
        for label, block in blocks.items()
    }

    def cost(order):
        saved = sum(edges.get(pair, 0) for pair in zip(order, order[1:]))
        estimate = -saved * machine["taken_branch_penalty"]
        cache_remaining = machine["icache_size"]
        for label in order:
            size = sizes[label]
            missed = max(0, size - cache_remaining)
            estimate += missed * visits[label] * machine["icache_penalty"]
            cache_remaining = max(0, cache_remaining - size)
        return estimate

    return candidate if cost(candidate) < cost(original) else None
