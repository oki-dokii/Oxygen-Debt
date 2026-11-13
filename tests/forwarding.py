"""Independent VM qualification for cross-block memory facts and peeled loops."""

import argparse
from collections import Counter
import json
from pathlib import Path
import random
import re
import subprocess
import sys
import tempfile

from stress import MACHINE_VARIANTS, make_inputs, make_program


def window(rng, index, sorting=False, base_override=None, mask_override=None):
    base = (0, 7, 3070, 4090, -2)[index % 5] if not sorting else (0, 64, 128, 512)[index % 4]
    delta = 1 if sorting else 1 + index % 3
    mask = 7 if not sorting else (7, 15, 31)[index % 3]
    if base_override is not None:
        base = base_override
    if mask_override is not None:
        mask = mask_override
    variant = 0 if sorting else index % 12
    blocks = {
        'entry': [f'and v3, v0, {mask}', 'const v2, 0', 'jmp outer'],
        'outer': [f'lt v21, v2, {"v3" if sorting else "3"}', 'br v21, start, done'],
        'start': ['const v4, 0', 'jmp head'],
        'head': ['sub v5, v3, 1' if sorting else 'mov v5, v3', 'lt v7, v4, v5', 'br v7, body, advance'],
        'body': [f'add v6, v4, {base}', 'load v8, v6', f'add v9, v6, {delta}',
                 'load v10, v9', 'lt v11, v10, v8', 'br v11, changed, join'],
        'changed': ['load v13, v6', 'load v15, v9', 'store v6, v15', 'store v9, v13', 'jmp join'],
        'join': ['add v17, v4, 1', 'mov v4, v17', 'jmp head'],
        'advance': ['add v2, v2, 1', 'jmp outer'],
        'done': ['ret v3'],
    }
    if variant == 1:
        blocks['changed'].insert(0, 'store v1, v0')
    elif variant == 2:
        blocks['changed'][0:0] = ['vload v8, 7', 'vstore 8, v8']
    elif variant == 3:
        blocks['changed'].insert(0, 'const v8, 17')
    elif variant == 4:
        blocks['changed'].insert(0, 'load v6, v6')
    elif variant == 5:
        blocks['changed'][0:0] = ['store 70, v0', 'div v22, v8, v1', 'vstore 8, v22']
    elif variant == 6:
        blocks['changed'].insert(0, 'mul v4, v4, 2')
    elif variant == 7:
        blocks['changed'].insert(0, 'sub v4, 31, v4')
    elif variant == 8:
        blocks['body'][-1] = 'br v11, changed, other'
        blocks['other'] = ['store v6, 0', 'jmp join']
    elif variant == 9:
        blocks['changed'].insert(0, 'store v6, v4')
    elif variant == 10:
        blocks['changed'][-1] = 'br v1, join, done'
    elif variant == 11:
        blocks['changed'][0:0] = ['add v25, v6, 4096', 'load v26, v25', 'vstore 8, v26']
    order = list(blocks)[1:]
    rng.shuffle(order)
    text = 'func window(v0, v1)\n' + ''.join(label + ':\n  ' + '\n  '.join(blocks[label]) + '\n'
                                                   for label in ['entry', *order])
    used = sorted(set(re.findall(r'\bv\d+\b', text)))
    renamed = dict(zip(used, [f'v{n}' for n in rng.sample(range(100, 1900), len(used))]))
    return re.sub(r'\bv\d+\b', lambda m: renamed[m[0]], text), (base, mask) if sorting else None


def affine_fixture(index):
    coefficient = (1, 3, 5, 17, 0xFFFFFFFF, 2, 4, 6)[index % 8]
    side = 'store v1, 9' if index % 2 else 'add v7, v4, 1\n  store v7, 9'
    return f"""func affine(v0, v1)
entry:
  mul v2, v0, {coefficient}
  add v2, v2, 7
  store 70, v1
  load v3, v2
  mul v0, v0, {coefficient}
  add v0, v0, v1
  sub v4, v0, v1
  add v4, v4, 7
  br v1, arm, done
arm:
  {side}
  jmp done
done:
  load v5, v4
  vstore 8, v5
  ret v5
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('kit', type=Path)
    parser.add_argument('--seed', type=int, default=618427)
    args = parser.parse_args()
    sys.dont_write_bytecode = True
    kit = args.kit.resolve()
    sys.path.insert(0, str(kit))
    import kirlib as ref
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    from src.forwarding import candidates, forward, join_copies
    from src.kirlib import parse_program
    from src.optimizer import optimize
    from src.peeling import candidates as peel
    rng = random.Random(args.seed)
    default = ref.load_machine(kit / 'machines/machine_default.cfg')
    machines = {p.stem: ref.load_machine(p) for p in sorted((kit / 'machines').glob('*.cfg'))}
    machines.update({name: default | settings for name, settings in MACHINE_VARIANTS.items()})
    forms, outcomes = Counter(), Counter()
    count = oracles = removed = 0
    with tempfile.TemporaryDirectory(prefix='oxygen-forwarding-') as directory:
        directory = Path(directory)
        src, out, cfg, prof = [directory / n for n in ('in.kir', 'out.kir', 'm.cfg', 'bad.prof')]
        prof.write_text('edge head advance 999999\nedge missing absent 99999\n')
        for index in range(136):
            if index < 32:
                source, _ = make_program(rng, index)
                oracle = None
            elif index < 120:
                source, oracle = window(rng, index - 32, sorting=index >= 104)
            else:
                source, oracle = affine_fixture(index - 120), None
            src.write_text(source)
            parsed = parse_program(source)
            original = ref.compile_program(ref.load_program(src))
            if index < 32:
                inputs = list(make_inputs(ref, rng))
            elif index >= 120:
                inputs = [ref.Inputs([value, other], [(0, [17, 19, 23, 29] * 64)], {8: [3]})
                          for value in (0, 1, 2, -1, 0x55555555, 0x80000000, 4090, 4096)
                          for other in (0, 1)]
            else:
                patterns = [list(range(256)), list(reversed(range(256))),
                            [0xFFFFFFFF, 0x80000000, 0, 1] * 64,
                            [rng.getrandbits(32) for _ in range(256)]]
                inputs = [ref.Inputs([n, address], [(0, pattern), (512, list(reversed(pattern))),
                                                     (3070, [0xFFFFFFFF, 2, 1]), (4095, [7])], {7: [17, 0, 1]})
                          for n in (0, 1, 7, 15) for address, pattern in zip((0, 1, 4096, -1), patterns)]
            references = [ref.execute(original, item.args, item.segments, item.vin, 200_000) for item in inputs]
            if any(before.status == 'TIMEOUT' for before in references):
                raise RuntimeError(f'reference timeout in fixture {index}')
            if oracle:
                base, mask = oracle
                for item, before in zip(inputs, references):
                    if before.status != 'RET':
                        continue
                    memory = [0] * 4096
                    for offset, words in item.segments:
                        memory[offset:offset+len(words)] = words
                    n = item.args[0] & mask
                    memory[base:base+n] = sorted(memory[base:base+n], key=lambda v: v if v < 2**31 else v - 2**32)
                    if before.mem[:3072] != memory[:3072]:
                        raise RuntimeError('sorting reference disagrees with mathematical oracle')
                    oracles += 1
            direct = forward(parsed)
            joined = join_copies(parsed)
            raw = [('direct', direct)] if direct else []
            if joined:
                raw.append(('join', joined))
                for peeled in peel(parse_program(joined)):
                    raw.append(('peel', peeled))
                    rewritten = forward(parse_program(peeled))
                    if rewritten:
                        raw.append(('composed', rewritten))
            for name, machine in machines.items():
                variants = raw[:]
                for text in candidates(parsed):
                    cleaned = optimize(parse_program(text), text, machine)
                    if cleaned:
                        variants.append(('cleaned', cleaned))
                cfg.write_text(''.join(f'{k} = {v}\n' for k, v in machine.items()))
                subprocess.run([root/'kopt', src, '--machine', cfg, '--profile', prof, '-o', out],
                               check=True, capture_output=True, timeout=5)
                variants.append(('CLI', out.read_text()))
                for kind, text in variants:
                    out.write_text(text)
                    program = ref.load_program(out)
                    ref.check_machine_features(program, machine)
                    optimized = ref.compile_program(program)
                    if kind == 'direct':
                        removed += sum(ins.op == 'load' for ins in parsed.instrs) - sum(ins.op == 'load' for ins in program.instrs)
                    forms[kind] += 1
                    for item, before in zip(inputs, references):
                        after = ref.execute(optimized, item.args, item.segments, item.vin, 20 * before.steps + 1000)
                        difference = ref.first_difference(before, after)
                        if difference:
                            failure = Path('/tmp/oxygen-forwarding-failure');failure.mkdir(exist_ok=True)
                            (failure/'input.kir').write_text(source);(failure/'output.kir').write_text(text)
                            (failure/'machine.json').write_text(json.dumps(machine))
                            (failure/'input.json').write_text(json.dumps(dict(args=item.args,segments=item.segments,vin=item.vin)))
                            raise RuntimeError(f'{index=} {name=} {kind=}: {difference}; artifacts {failure}')
                        count += 1
                        outcomes[before.status if before.status == 'RET' else
                                 'explicit_trap' if before.value.startswith('explicit(') else before.value] += 1
    if not removed or not forms['composed'] or not oracles:
        raise RuntimeError('suite did not exercise forwarding, compositions and sorting oracle')
    print(f'136 forwarding fixtures × {len(machines)} machines: {count:,} direct/join/peeled/composed/cleaned/CLI matches; '
          f'{oracles} sorting oracles; forms {dict(forms)}; removed loads across direct pairs {removed}; '
          f'outcomes {dict(outcomes)}; 0 reference timeouts (seed {args.seed})')


if __name__ == '__main__':
    main()
