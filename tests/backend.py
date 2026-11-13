"""Check every backend form, including unselected schedules, with the external VM."""

import argparse
from collections import Counter
from pathlib import Path
import random
import re
import subprocess
import sys
import tempfile

from stress import MACHINE_VARIANTS, make_inputs, make_program


def fixture(rng, index):
    blocks = {
        'entry': ['and v3, v3, 7', 'const v10, 0', 'br v2, left, right'],
        'left': ['add v11, v0, 3', 'mov v12, v11', 'store 1, v12', 'jmp head'],
        'right': ['add v13, v1, 5', 'mov v12, v13', 'const v11, 97', 'jmp head'],
        'head': ['lt v14, v10, v3', 'br v14, first, done'],
        'first': ['add v15, v0, 7', 'mul v16, v1, 9', 'xor v17, v15, v16',
                  'add v12, v12, v17', 'jmp second'],
        'second': ['add v10, v10, 1', 'store 2, v12', 'jmp head'],
        'done': ['xor v18, v12, v11', 'add v19, v18, v21', 'vstore 7, v19', 'ret v19'],
    }
    if index % 8 == 0:
        # Two entries to the cycle, one bypassing a definition.
        blocks['right'][-1] = 'jmp second'
    if index % 8 == 1:
        blocks['second'].insert(0, 'div v20, v12, v2')
        blocks['second'].insert(1, 'vstore 8, v20')
    if index % 8 == 2:
        blocks['second'].insert(0, 'load v20, v0')
        blocks['second'].insert(1, 'add v12, v12, v20')
    if index % 8 == 3:
        blocks['first'].insert(0, 'vload v15, 7')
        blocks['first'].insert(1, 'vstore 8, v15')
    if index % 8 == 4:
        blocks['done'][-1] = 'trap v19'
    if index % 8 == 5:
        # Dead write may not overwrite a still-live value after coalescing.
        blocks['first'].insert(3, 'const v30, 99')
    if index % 8 == 6:
        blocks['second'][0:0] = ['mov v0, v12', 'xor v0, v0, v1']
    if index % 8 == 7:
        # Read-before-write plus register swaps and multiple reaching definitions.
        blocks['first'][0:0] = ['mov v30, v11', 'mov v11, v12', 'mov v12, v30']
    if index >= 48:
        for _ in range(18):
            op = rng.choice(('add', 'xor', 'mul', 'shl', 'lt', 'select'))
            dest = rng.randrange(22, 38)
            left = rng.choice((0, 1, 11, 12, 15, 16, 17, 21, dest))
            right = rng.choice((0, 1, 11, 12, 15, 16, 17, 21, dest))
            ins = f'{op} v{dest}, v{left}, v{right}' + (', v2' if op == 'select' else '')
            blocks['first'].insert(-1, ins)
            blocks['done'].insert(-1, f'xor v19, v19, v{dest}')
    order = list(blocks)[1:]
    rng.shuffle(order)
    text = 'func backend(v0, v1, v2, v3)\n' + ''.join(
        label + ':\n  ' + '\n  '.join(blocks[label]) + '\n' for label in ['entry', *order])
    names = sorted(set(re.findall(r'\bv\d+\b', text)))
    renamed = dict(zip(names, [f'v{n}' for n in rng.sample(range(100, 1200), len(names))]))
    return re.sub(r'\bv\d+\b', lambda m: renamed[m[0]], text)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('kit', type=Path)
    parser.add_argument('--seed', type=int, default=732619)
    args = parser.parse_args()
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(args.kit.resolve()))
    import kirlib as ref
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    from src.backend import candidates
    from src.global_registers import colour, split_lifetimes
    from src.kirlib import parse_program
    from src.optimizer import render_canonical
    from src.schedule import scheduled_order
    rng = random.Random(args.seed)
    default = ref.load_machine(args.kit / 'machines/machine_default.cfg')
    machines = {path.stem: ref.load_machine(path) for path in sorted((args.kit / 'machines').glob('*.cfg'))}
    machines.update({name: default | fields for name, fields in MACHINE_VARIANTS.items()})
    matches, changed, outcomes, forms = 0, Counter(), Counter(), Counter()
    with tempfile.TemporaryDirectory(prefix='oxygen-backend-') as directory:
        directory = Path(directory)
        src, out, config, profile = [directory / name for name in ('in.kir', 'out.kir', 'm.cfg', 'wrong.prof')]
        profile.write_text('edge entry right 99999\nedge head done 99999\nedge missing absent 99999\n')
        for index in range(120):
            source = make_program(rng, index)[0] if index < 40 else fixture(rng, index - 40)
            src.write_text(source)
            original = ref.compile_program(ref.load_program(src))
            inputs = list(make_inputs(ref, rng))
            references = [ref.execute(original, item.args, item.segments, item.vin, 5000) for item in inputs]
            if any(run.status == 'TIMEOUT' for run in references):
                raise RuntimeError(f'reference timeout: {index}')
            program = parse_program(source)
            starts = [program.labels[label] for label in program.block_labels]
            blocks = {label: program.instrs[start:end] for label, start, end in zip(
                program.block_labels, starts, starts[1:] + [len(program.instrs)])}
            split = split_lifetimes(blocks, program.params)
            for name, mc in machines.items():
                variants = []
                for strategy in ('saturation', 'degree'):
                    allocated = colour(blocks, program.params, strategy)
                    if allocated is not None:
                        variants.append(('allocation', render_canonical(program, allocated, program.block_labels, {})))
                if split is not None:
                    variants.append(('webs', render_canonical(program, split, program.block_labels, {})))
                    allocated = colour(split, program.params)
                    if allocated is not None:
                        variants.append(('web_allocation', render_canonical(program, allocated, program.block_labels, {})))
                # Direct permutations bypass profitability filters, proving even
                # schedules not selected by the timing contexts preserve effects.
                for mode in ('pressure', 'pressure_first'):
                    scheduled = {}
                    for label, block in blocks.items():
                        permutation = scheduled_order(block, mc, mode)
                        scheduled[label] = [block[n] for n in permutation] if permutation else block
                        changed[mode] += permutation is not None
                    variants.append((mode, render_canonical(program, scheduled, program.block_labels, {})))
                variants += [('portfolio', text) for text in candidates(source, mc)]
                config.write_text(''.join(f'{key} = {value}\n' for key, value in mc.items()))
                subprocess.run([root / 'kopt', src, '--machine', config, '--profile', profile, '-o', out],
                               check=True, capture_output=True, timeout=5)
                variants.append(('CLI', out.read_text()))
                for kind, text in variants:
                    out.write_text(text)
                    optimized = ref.compile_program(ref.load_program(out))
                    forms[kind] += 1
                    for item, before in zip(inputs, references):
                        after = ref.execute(optimized, item.args, item.segments, item.vin, 20 * before.steps + 1000)
                        diff = ref.first_difference(before, after)
                        if diff:
                            failure = Path('/tmp/oxygen-backend-failure')
                            failure.mkdir(exist_ok=True)
                            (failure/'input.kir').write_text(source)
                            (failure/'output.kir').write_text(text)
                            raise RuntimeError(f'{index=} {name=} {kind=}: {diff}; {item}; artifacts: {failure}')
                        matches += 1
                        outcomes[before.status if before.status == 'RET' else
                                 'explicit_trap' if before.value.startswith('explicit(') else before.value] += 1
    if not all(changed[mode] for mode in ('pressure', 'pressure_first')) or not forms['web_allocation']:
        raise RuntimeError('suite did not exercise all backend proof forms')
    print(f'120 fresh backend fixtures × {len(machines)} machines × 12 inputs: {matches:,} matches; '
          f'forms {dict(forms)}; reordered blocks {dict(changed)}; outcomes {dict(outcomes)}; '
          f'0 reference timeouts (seed {args.seed})')


if __name__ == '__main__':
    main()
