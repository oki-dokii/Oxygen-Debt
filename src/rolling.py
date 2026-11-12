"""Reuse proven affine memory values across a simple counting loop."""

from .kiln import compile_program, time_trace
from .kirlib import MASK, Instr, Program, SIGS
from .loops import double_loops
from .ranges import entry_intervals, interval, signed, update
from .registers import register_names, register_reads


def affine(op, sources):
    if any(value is None for value in sources):
        return None
    if op in {"const", "mov"}:
        return sources[0]
    if op in {"add", "sub"}:
        sign = -1 if op == "sub" else 1
        return tuple((a + sign * b) & MASK for a, b in zip(*sources))
    if op in {"mul", "shl", "addsh", "mac"}:
        if op == "shl":
            if sources[1][0]:
                return None
            return affine("mul", [sources[0], (0, 1 << (sources[1][1] & 31))])
        if op == "addsh":
            return affine("add", [sources[0], affine("mul", [sources[1], (0, 1 << sources[2][1])])])
        left, right = sources[:2]
        if left[0] and right[0]:
            return None
        product = ((left[0] * right[1] + right[0] * left[1]) & MASK,
                   left[1] * right[1] & MASK)
        return affine("add", [product, sources[2]]) if op == "mac" else product
    return None


def disjoint(left, right, low, high):
    if left is None or right is None:
        return False
    if left[0] == right[0]:
        return left[1] != right[1]

    def span(value):
        a, b = map(signed, value)
        ends = a * low + b, a * high + b
        lo, hi = min(ends), max(ends)
        return (lo, hi) if 0 <= lo <= hi <= MASK else None

    a, b = span(left), span(right)
    return a is not None and b is not None and (a[1] < b[0] or b[1] < a[0])


def model(blocks, order, params):
    program = Program()
    program.name = "rolling_model"
    program.params = list(params)
    indices = {}
    for label in order:
        start = len(program.instrs)
        program.labels[label] = start
        program.block_labels.append(label)
        program.instrs.extend(blocks[label])
        program.block_of.extend([label] * len(blocks[label]))
        indices[label] = range(start, len(program.instrs))
    return compile_program(program), indices


def reuse_loop_loads(blocks, order, params, machine, pure):
    if machine["lat_load"] <= machine["lat_alu"] or sum(map(len, blocks.values())) > 5000:
        return False
    predecessors = {label: [] for label in blocks}
    written = {}
    for label, block in blocks.items():
        for target in dict.fromkeys(value for kind, value in block[-1].args if kind == "l"):
            predecessors[target].append(label)
        written[label] = {ins.args[0][1] for ins in block if SIGS[ins.op].startswith("d")}
    facts_at_entry = entry_intervals(blocks)
    names = register_names(ins for block in blocks.values() for ins in block) | set(params)
    if machine["reg_spill_penalty"] and len(names) + 1 > machine["registers"]:
        return False
    next_register = max(names, default=-1) + 1
    next_line = max(ins.line for block in blocks.values() for ins in block) + 1
    budget = 200_000
    changed = False
    for head, header in list(blocks.items()):
        if (head == order[0] or len(header) < 2 or header[-2].op != "lt" or header[-1].op != "br"
                or header[-1].args[0] != header[-2].args[0]):
            continue
        body_label, exit_label = (arg[1] for arg in header[-1].args[1:])
        if body_label in (order[0], head, exit_label) or predecessors[body_label] != [head]:
            continue
        body = blocks[body_label]
        if (len(body) > 128 or body[-1].op != "jmp" or body[-1].args != [("l", head)]
                or len(predecessors[head]) != 2
                or any(ins.op in {"vload", "vstore"} for ins in body)):
            continue
        preheader = next(label for label in predecessors[head] if label != body_label)
        if blocks[preheader][-1].op != "jmp":
            continue
        condition, counter, bound = header[-2].args
        if counter[0] != "r" or condition == counter:
            continue
        loop_writes = written[head] | written[body_label]
        invariant = set()
        valid = True
        for ins in header[:-2]:
            if (ins.op not in pure or ins.args[0] == counter
                    or any(r in loop_writes and r not in invariant for r in register_reads(ins))):
                valid = False
                break
            invariant.add(ins.args[0][1])
        if not valid or (bound[0] == "r" and bound[1] in loop_writes and bound[1] not in invariant):
            continue
        facts = facts_at_entry.get(preheader, {}).copy()
        for ins in blocks[preheader][:-1]:
            update(facts, ins.op, ins.args)
        initial, initial_high = interval(facts, counter)
        for ins in header[:-2]:
            update(facts, ins.op, ins.args)
        bound_low, bound_high = interval(facts, bound)
        if initial != initial_high or not 0 <= initial < bound_high <= 4096 or bound_low < 0:
            continue
        values = {r: (0, lo & MASK) for r, (lo, hi) in facts.items() if lo == hi and r not in written[body_label]}
        # Header definitions are current, but a local overwritten in the body is not an invariant.
        for r in invariant:
            lo, hi = interval(facts, ("r", r))
            if lo == hi:
                values[r] = (0, lo & MASK)
        values[counter[1]] = (1, 0)
        values[condition[1]] = (0, 1)
        accesses = []
        for index, ins in enumerate(body[:-1]):
            def read(operand):
                return values.get(operand[1]) if operand[0] == "r" else (0, operand[1])

            if ins.op in {"load", "store"}:
                accesses.append((index, ins, read(ins.args[1] if ins.op == "load" else ins.args[0])))
            if SIGS[ins.op].startswith("d"):
                values[ins.args[0][1]] = affine(ins.op, [read(arg) for arg in ins.args[1:]])
        step = values.get(counter[1])
        if step is None or step[0] != 1 or not 1 <= step[1] <= 4096:
            continue
        pairs = []
        for index, load, address in accesses:
            if load.op != "load" or address is None:
                continue
            initial_address = (address[0] * initial + address[1]) & MASK
            if initial_address >= 4096:
                continue
            future = address[0], (address[1] + address[0] * step[1]) & MASK
            suppliers = [(i, ins) for i, ins, addr in accesses if addr == future
                         and (i > index or (i == index and address[0] == 0))]
            if not suppliers:
                continue
            supplier_index, supplier = suppliers[-1]
            if any(ins.op == "store" and (
                (i < index and not disjoint(addr, address, initial, bound_high - 1))
                or (i > supplier_index and not disjoint(addr, future, initial, bound_high - 1)))
                   for i, ins, addr in accesses):
                continue
            pairs.append((index, load, initial_address, supplier_index, supplier))
            if len(pairs) == 4:
                break
        choices = [(pair,) for pair in pairs[:4]]
        if len(pairs) >= 2:
            choices.append(tuple(pairs[:2]))
        if not choices:
            continue
        paths = [(preheader, *(label for _ in range(count) for label in (head, body_label)), head, exit_label)
                 for count in (2, 8)]
        count = sum(map(len, blocks.values()))
        work = 3 * count + sum(sum(len(blocks[label]) for label in path) for path in paths)
        if work > budget:
            continue
        budget -= work
        original, original_indices = model(blocks, order, params)
        existing_doubles = double_loops(blocks, order, machine).keys()
        old_times = [time_trace(original, [pc for label in path for pc in original_indices[label]], machine)
                     for path in paths]
        best_score = sum(old_times)
        best = None
        for selected in choices:
            if next_register + len(selected) > 1_000_000:
                continue
            if (machine["reg_spill_penalty"] and original.nregs + len(selected) > machine["registers"]):
                continue
            preload, replacements, captures = [], {}, {}
            line = next_line
            for offset, (index, load, address, supplier_index, supplier) in enumerate(selected):
                carry = ("r", next_register + offset)
                preload.append(Instr("load", [carry, ("i", address)], line, ""))
                line += 1
                replacements[index] = Instr("mov", [load.args[0], carry], load.line, load.text)
                if supplier_index != index:
                    source = supplier.args[0] if supplier.op == "load" else supplier.args[1]
                    captures.setdefault(supplier_index, []).append(Instr(
                        "mov" if source[0] == "r" else "const", [carry, source], line, ""))
                    line += 1
            candidate = blocks.copy()
            candidate[preheader] = blocks[preheader][:-1] + preload + blocks[preheader][-1:]
            candidate[body_label] = [item for i, ins in enumerate(body)
                                     for item in (replacements.get(i, ins), *captures.get(i, ()))]
            count = sum(map(len, candidate.values()))
            if machine["icache_penalty"] and count > machine["icache_size"]:
                continue
            if not existing_doubles <= double_loops(candidate, order, machine).keys():
                continue
            work = 4 * count + sum(sum(len(candidate[label]) for label in path) for path in paths)
            if work > budget:
                continue
            budget -= work
            compiled, indices = model(candidate, order, params)
            times = [time_trace(compiled, [pc for label in path for pc in indices[label]], machine) for path in paths]
            if all(new <= old for new, old in zip(times, old_times)) and sum(times) < best_score:
                best_score, best = sum(times), (candidate, line, len(selected))
        if best is not None:
            candidate, next_line, added = best
            blocks.update(candidate)
            next_register += added
            changed = True
    return changed
