"""Independent proof/complete-compiler checks for deferred checksum remainders."""
import argparse
from collections import Counter
from pathlib import Path
import random
import subprocess
import sys
import tempfile

from stress import MACHINE_VARIANTS


def source(rng, number, modulus=65521, count_mask=63, payload_mask=255, scale=1,
           weight=1, square=False, base=0, initial=1, second=0, variant="plain"):
    registers = [f"v{r}" for r in rng.sample(range(20, 900), 10)]
    n, i, cond, a, b, address, value, first, term, output = registers
    entry, head, body, done = [f"case_{number}_{suffix}" for suffix in ("entry", "head", "body", "done")]
    setup = [f"and {n}, v0, {count_mask}", f"const {i}, 0"]
    if variant == "unknown_initial": setup += [f"mov {a}, v1"]
    elif variant == "masked_initial": setup += [f"and {a}, v1, 255"]
    else: setup += [f"const {a}, {initial}"]
    setup += [f"const {b}, {second}", f"const {first}, 0", f"store 700, {a}", f"vstore 7, {b}"]
    setup += [f"br v1, {head}, {done}" if variant == "shared_exit" else f"jmp {head}"]
    operations = [f"add {address}, {i}, {base}", f"load {value}, {a if variant == 'tainted_address' else address}"]
    if variant != "unmasked": operations += [f"and {value}, {value}, {payload_mask}"]
    operations += [f"mul {value}, {value}, {scale}", f"add {first}, {a}, {value}", f"mod {a}, {first}, {modulus}"]
    if variant == "nonlinear_use": operations += [f"and {a}, {a}, 15"]
    if variant == "tainted_shift": operations += [f"shl {term}, 1, {a}"]
    elif variant in ("selector", "tainted_select"):
        operations += [f"and {value}, {value}, 1", f"select {term}, {a if variant == 'tainted_select' else value}, {a}, {b}"]
    elif square: operations += [f"mul {term}, {a}, {a}"]
    else: operations += [f"mul {term}, {a}, {weight}"]
    operations += [f"{'sub' if variant == 'subtract' else 'add'} {term}, {b}, {term}",
                   f"mod {b}, {term}, {modulus+2 if variant == 'different_moduli' else modulus}"]
    if variant == "store": operations += [f"store 701, {a}"]
    if variant == "volatile": operations += [f"vstore 8, {a}"]
    if variant == "division": operations += [f"div {value}, {a}, v1"]
    operations += [f"add {i}, {i}, {a if variant == 'tainted_counter' else '1'}", f"jmp {head}"]
    ending = [f"ret {first}"] if variant == "raw_temporary" else [f"shl {output}, {b}, 16", f"or {output}, {output}, {a}", f"ret {output}"]
    blocks = {entry: setup, head: [f"lt {cond}, {i}, {n}", f"br {cond}, {body}, {done}"], body: operations, done: ending}
    rest = [head, body, done]; rng.shuffle(rest)
    return "func checksum(v0, v1)\n" + "".join(label+":\n  "+"\n  ".join(blocks[label])+"\n" for label in [entry,*rest])


def late_taint_source():
    # tmp is M on the first exit (untainted), but tainted/canonical on later
    # exits. Normalizing only the tainted-exit snapshots would be unsound.
    return ('func checksum(v0, v1)\nentry:\n  and v0, v0, 3\n  const v2, 6\n  const v3, 0\n  const v4, 0\n  jmp head\n'
            'head:\n  lt v5, v4, v0\n  br v5, body, done\nbody:\n  add v3, v2, 1\n  mod v2, v3, 7\n  add v4, v4, 1\n  jmp head\n'
            'done:\n  ret v3\n')


def wrapped_constant_source():
    # 7*700000000 wraps to a positive word. A folded word interval must not
    # be mistaken for a proof that the mathematical product did not wrap.
    return ('func checksum(v0, v1)\nentry:\n  const v2, 6\n  const v3, 0\n  jmp head\n'
            'head:\n  lt v4, v3, 1\n  br v4, body, done\nbody:\n  add v2, v2, 1\n  mod v2, v2, 7\n'
            '  mul v2, v2, 700000000\n  mod v2, v2, 7\n  add v3, v3, 1\n  jmp head\ndone:\n  ret v2\n')


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('kit',type=Path);args=parser.parse_args()
    kit=args.kit.resolve();sys.dont_write_bytecode=True
    sys.path.insert(0,str(kit));sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    import kirlib as ref
    from src.kirlib import parse_program
    from src.modulo import defer_moduli
    from src.optimizer import PURE, optimize, render_canonical
    rng=random.Random(327419)
    default=ref.load_machine(kit/'machines/machine_default.cfg')
    machines={p.stem:ref.load_machine(p) for p in sorted((kit/'machines').glob('*.cfg'))}
    machines.update({name:default|values for name,values in MACHINE_VARIANTS.items()})
    cases=[(dict(modulus=m,count_mask=count),True) for m in (7,31,255,65521) for count in (3,15,63)]
    cases += [(dict(weight=3,scale=2),True), (dict(modulus=31,count_mask=15,payload_mask=3,square=True),True),
              (dict(count_mask=255,payload_mask=65535),True),
              (dict(base=3072),True), (dict(modulus=7,count_mask=3,base=4095,initial=6,second=6),True),
              (dict(variant='masked_initial'),True),
              (dict(count_mask=3,payload_mask=0),True),
              (dict(variant='selector',modulus=31,count_mask=7,payload_mask=3),True),
              (dict(variant='tainted_select',modulus=7,count_mask=3,payload_mask=7,initial=0,second=1),False)]
    cases += [(dict(variant=variant,modulus=7,count_mask=3,payload_mask=7,initial=0,second=1),False)
              for variant in ('tainted_shift',)]
    cases += [(dict(variant=variant),False) for variant in ('unknown_initial','unmasked','store','volatile','division',
                                                          'nonlinear_use','subtract','tainted_address','tainted_counter',
                                                          'different_moduli','shared_exit','raw_temporary')]
    cases += [(dict(initial=65521),False),(dict(initial=-1),False),
              (dict(count_mask=511),True),(dict(count_mask=1023),True),(dict(count_mask=2047),False),
              (dict(count_mask=255,payload_mask=65535,scale=2),False),
              (dict(modulus=-65521),False)]
    # raw_temporary is canonical for some small counts, but not for this whole
    # domain: original numerator may exceed the modulus after a reduced state.
    cases=[(settings|({'modulus':7,'count_mask':3,'initial':6} if settings.get('variant')=='raw_temporary' else {}),accept)
           for settings,accept in cases]
    cases=[(settings|({'modulus':31} if settings.get('variant')=='nonlinear_use' else {})
                     |({'modulus':7,'count_mask':3} if settings.get('variant')=='tainted_address' else {}),accept)
           for settings,accept in cases]
    fixtures=[(source(rng,i,**settings),settings,accept) for i,(settings,accept) in enumerate(cases)]
    fixtures.append((late_taint_source(),{'variant':'late_taint'},False))
    fixtures.append((wrapped_constant_source(),{'variant':'wrapped_constant'},False))
    comparisons=transformed=zero=skipped=0;outcomes=Counter();changed_outcomes=Counter()
    with tempfile.TemporaryDirectory(prefix='oxygen-modulo-') as folder:
        work=Path(folder);inp=work/'in.kir';out=work/'out.kir'
        for name,mc in machines.items():(work/f'{name}.cfg').write_text(''.join(f'{k} = {v}\n' for k,v in mc.items()))
        patterns=[[0]*4096,[0xFFFFFFFF]*4096,[0x80000000,0x7FFFFFFF]*2048,[rng.getrandbits(32) for _ in range(4096)]]
        for index,(text,settings,accept) in enumerate(fixtures):
            inp.write_text(text);original=ref.compile_program(ref.load_program(inp))
            words=[0,1,2,3,7,15,31,63,255,0x80000000,0xFFFFFFFF,*[rng.getrandbits(32) for _ in range(5)]]
            words[13] = settings.get('count_mask',63)
            values=[[word,(0,1,65520,65521,0xFFFFFFFF,0x80000000)[i%6]] for i,word in enumerate(words)]
            inputs=[(v,[(0,patterns[i%4])],{7:[11,13]}) for i,v in enumerate(values)]
            references=[ref.execute(original,*data,100000) for data in inputs]
            if any(run.status=='TIMEOUT' for run in references):
                # Deliberately corrupting the induction update can make the
                # source nonterminating. Keep rejection checks; do not count it.
                if settings.get('variant')!='tainted_counter':raise RuntimeError('unexpected reference timeout')
            if accept:
                for (v,segments,_),run in zip(inputs,references):
                    if run.status!='RET':continue
                    m=settings.get('modulus',65521);n=v[0]&settings.get('count_mask',63)
                    a=(v[1]&255) if settings.get('variant')=='masked_initial' else settings.get('initial',1)
                    b=settings.get('second',0);base=settings.get('base',0)
                    memory=segments[0][1].copy()
                    memory[700]=a&0xFFFFFFFF
                    for i in range(n):
                        payload=(memory[base+i]&settings.get('payload_mask',255))*settings.get('scale',1)
                        a=(a+payload)%m
                        contribution=(a if payload&1 else b) if settings.get('variant')=='selector' else (a*a if settings.get('square') else settings.get('weight',1)*a)
                        b=(b+contribution)%m
                    expected=((b<<16)|a)&0xFFFFFFFF
                    if run.value!=expected:raise RuntimeError(f'oracle mismatch: {index}, {v}, {run.value}, {expected}')
            program=parse_program(text);starts=[program.labels[label] for label in program.block_labels]
            blocks={label:program.instrs[a:b] for label,a,b in zip(program.block_labels,starts,[*starts[1:],len(program.instrs)])}
            changed=defer_moduli(blocks,PURE)
            if bool(changed)!=accept:raise RuntimeError(f'proof expectation mismatch: {index}, {settings}, {bool(changed)}')
            transformed+=bool(changed)
            out.write_text(render_canonical(program,blocks,program.block_labels,{}));direct=ref.compile_program(ref.load_program(out))
            for name,mc in machines.items():
                candidate=optimize(parse_program(text),text,mc,{},frozenset({'defer_mod'}))
                candidate_path=work/'candidate.kir';candidate_path.write_text(candidate if candidate is not None else text)
                parsed=ref.load_program(candidate_path);ref.check_machine_features(parsed,mc);unselected=ref.compile_program(parsed)
                subprocess.run([Path(__file__).resolve().parents[1]/'kopt',inp,'--machine',work/f'{name}.cfg','-o',out],
                               check=True,capture_output=True,timeout=5)
                parsed=ref.load_program(out);ref.check_machine_features(parsed,mc);selected=ref.compile_program(parsed)
                for data,before in zip(inputs,references):
                    if before.status=='TIMEOUT':skipped+=1;continue
                    for kind,compiled in (('direct',direct),('unselected',unselected),('selected',selected)):
                        after=ref.execute(compiled,*data,100000)
                        difference=ref.first_difference(before,after)
                        if difference:raise RuntimeError(f'{index}, {settings}, {name}, {data[0]}, {kind}: {difference}\n{text}')
                        comparisons+=1
                    result=before.status if before.status=='RET' else before.value
                    outcomes[result]+=1
                    if changed:
                        changed_outcomes[result]+=1
                        zero+=(data[0][0]&settings.get('count_mask',63))==0
    if not zero or not changed_outcomes['bad_address']:raise RuntimeError('missing transformed zero-trip/trap coverage')
    print(f'{len(fixtures)} modulo fixtures × {len(machines)} machines × 16 inputs: {comparisons:,} direct/unselected/selected matches; '
          f'{transformed} proved fixtures, {zero} transformed zero-trip checks; {skipped} reference timeouts skipped; '
          f'outcomes {dict(outcomes)}; transformed {dict(changed_outcomes)}')

if __name__=='__main__':main()
