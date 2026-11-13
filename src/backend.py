"""Independent allocation/scheduling candidates after the established portfolio."""

from .global_registers import colour, split_lifetimes
from .kirlib import parse_program
from .optimizer import render_canonical
from .schedule import schedule_blocks


def candidates(source, machine):
    program = parse_program(source)
    if len(program.instrs) > 2048 or len(program.block_labels) > 128:
        return []
    starts = [program.labels[label] for label in program.block_labels]
    blocks = {label: program.instrs[start:end] for label, start, end in zip(
        program.block_labels, starts, starts[1:] + [len(program.instrs)])}
    results = []
    for strategy in ('saturation', 'degree'):
        allocated = colour(blocks, program.params, strategy)
        if allocated is not None:
            results.append(render_canonical(program, allocated, program.block_labels, {}))
            if strategy == 'saturation':
                if schedule_blocks(allocated, program.block_labels, program.params, machine, 'pressure'):
                    results.append(render_canonical(program, allocated, program.block_labels, {}))
    split = split_lifetimes(blocks, program.params)
    if split is not None:
        allocated = colour(split, program.params)
        if allocated is not None:
            results.append(render_canonical(program, allocated, program.block_labels, {}))
            if schedule_blocks(allocated, program.block_labels, program.params, machine, 'pressure'):
                results.append(render_canonical(program, allocated, program.block_labels, {}))
    for mode in ('pressure', 'pressure_first'):
        scheduled = {label: block[:] for label, block in blocks.items()}
        if schedule_blocks(scheduled, program.block_labels, program.params, machine, mode):
            results.append(render_canonical(program, scheduled, program.block_labels, {}))
            allocated = colour(scheduled, program.params)
            if allocated is not None:
                results.append(render_canonical(program, allocated, program.block_labels, {}))
    return list(dict.fromkeys(results))
