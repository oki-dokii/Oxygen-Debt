"""Bounded deterministic timing selection; profiles affect weights, never proofs."""

from collections import Counter

from .kiln import compile_program, execute, time_trace
from .kirlib import KirError, check_machine_features, parse_program


def cases(nparams):
    seed = 0x6495AB23
    values = []
    for _ in range(4096):
        seed = (1664525 * seed + 1013904223) & 0xFFFFFFFF
        values.append(seed)
    edges = (0, 1, 2, 7, 15, 31, 0xFFFFFFFF, 0x80000000)
    for index in range(16):
        if index < 8:
            args = [edges[(index + p) % len(edges)] for p in range(nparams)]
        else:
            args = []
            for _ in range(nparams):
                seed = (1664525 * seed + 1013904223) & 0xFFFFFFFF
                args.append(seed)
        memory = [0] * 4096 if index == 0 else values if index % 2 else list(reversed(values))
        yield args, [(0, memory)], {7: [index, 1, 0, 0xFFFFFFFF]}


def select(program, sources, machine, profile):
    """Keep the original if a complete bounded comparison cannot establish a gain."""
    original = compile_program(program)
    inputs, references, times, edge_counts = [], [], [], []
    budget = 100_000
    for args, memory, volatile in cases(len(program.params)):
        run = execute(original, args, memory, volatile, min(20_000, max(1,budget)), want_trace=True)
        budget -= run.steps
        if run.status == "TIMEOUT":
            continue
        inputs.append((args,memory,volatile)); references.append(run)
        times.append(time_trace(original, run.trace, machine))
        counts = Counter((original.block_of[a],original.block_of[b]) for a,b in zip(run.trace,run.trace[1:])
                         if original.isterm[a])
        edge_counts.append(counts)
        if budget <= 0: break
    if len(inputs) < 2:
        return None
    weights = [1] * len(inputs)
    valid = {(label, target) for ins,label in zip(program.instrs, program.block_of)
             for kind,target in ins.args if kind == "l"}
    hints = {edge: count for edge,count in profile.items() if edge in valid}
    if hints:
        total = sum(hints.values())
        def distance(index):
            counts = edge_counts[index]; visits = sum(counts.values())
            return sum(abs(counts.get(edge,0)*total-hints.get(edge,0)*visits) for edge in counts.keys() | hints.keys())
        for index in sorted(range(len(inputs)),key=lambda i:(distance(i),i))[:4]: weights[index] = 2
    best_score = 1
    for time,weight in zip(times,weights): best_score *= time ** weight
    best = None
    work = 500_000
    for source in dict.fromkeys(sources):
        try:
            parsed = parse_program(source)
            check_machine_features(parsed, machine)
            if len(parsed.params) != len(program.params):
                continue
            compiled = compile_program(parsed)
        except KirError:
            continue
        score = 1
        for values, reference, weight in zip(inputs, references, weights):
            args,memory,volatile = values
            run = execute(compiled, args, memory, volatile, min(max(1,work),20*reference.steps+1000), want_trace=True)
            work -= run.steps
            if (run.status != reference.status or run.value != reference.value or run.vlog != reference.vlog
                    or run.mem[:3072] != reference.mem[:3072]):
                break
            score *= time_trace(compiled,run.trace,machine) ** weight
            if work <= 0: return best
        else:
            if score < best_score:
                best_score, best = score, source
    return best
