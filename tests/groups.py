"""Direct counted-group proofs and optimized candidates against the external VM."""

import argparse
from collections import Counter
from pathlib import Path
import random
import re
import subprocess
import sys
import tempfile

from stress import MACHINE_VARIANTS


def source(stride=1,start=0,base=256,variant='plain',mask=63,minimum=0):
    setup=[f'and v2, v0, {mask}',f'const v3, {start}',f'const v4, {stride}',
           'mov v5, v1','store 700, v0','vstore 7, v1','jmp head']
    if variant=='variable':setup[2:3]=['and v4, v1, 3','add v4, v4, 1']
    if variant=='signed_bound':setup[0]='mov v2, v0'
    if variant=='unknown_step':setup[2]='mov v4, v1'
    if variant=='near_max':setup[0]='const v2, 2147483644'
    if variant=='overflow':setup[0]='const v2, 2147483647'
    if minimum:setup.insert(1,f'add v2, v2, {minimum}')
    body=[f'add v7, v3, {base}','store v7, v5','load v8, v7','add v5, v5, v8']
    if variant=='near_max':body=['add v5, v5, v3']
    if variant in ('bad_address','unknown_step','overflow'):body[2]='load v8, 4096'
    if variant=='division':body+=['div v5, v5, v1']
    if variant=='volatile':body+=['vstore 9, v6','vload v6, 7','add v5, v5, v6']
    if variant=='counter_data':body+=['add v5, v5, v3']
    if variant=='carry_temp':body.insert(0,'add v5, v5, v9')
    if variant=='change_bound':body+=['const v2, 0']
    if variant=='change_step':body+=['const v4, 2']
    if variant=='two_writes':body+=['add v3, v3, 1']
    update=['add v9, v3, v4','mov v3, v9']
    if variant=='inplace':update=['add v3, v3, v4']
    if variant=='predicate_update':update=['add v6, v3, v4','mov v3, v6']
    if variant=='predicate_step':update=['add v9, v3, v6','mov v3, v9']
    blocks={'entry':setup,'head':['lt v6, v3, v2','br v6, body, done'],
            'body':body+update+['jmp head'],
            'done':['add v5, v5, v3','add v5, v5, v6','add v5, v5, v9','ret v5']}
    if variant=='wrong_backedge':blocks['body'][-1]='jmp done'
    text='func generated(v0, v1)\n'+''.join(label+':\n  '+'\n  '.join(items)+'\n' for label,items in blocks.items())
    if variant=='entry_body':
        text='func generated(v0, v1)\n'+''.join(label+':\n  '+'\n  '.join(blocks[label])+'\n' for label in ('body','entry','head','done'))
    return text


def fixtures():
    result=[]
    for stride in (1,2,3,7):
        for start in (0,1,5):result.append((source(stride,start),True))
    for variant in ('variable','inplace','predicate_update','volatile','carry_temp','counter_data','bad_address','division'):
        result.append((source(variant=variant),True))
    result += [(source(2,2147483620,variant='near_max'),True),
               (source(2,0,variant='overflow'),False)]
    for variant in ('signed_bound','unknown_step','change_bound','change_step','two_writes','predicate_step','wrong_backedge','entry_body'):
        result.append((source(variant=variant),False))
    result += [(source(0,variant='bad_address'),False),(source(-1,variant='bad_address'),False),
               (source(4097),False),(source(start=-1),False)]
    for variant in ('plain','variable','volatile','predicate_update','division','counter_data'):
        result.append((source(variant=variant,minimum=128),True))
    rng=random.Random(438171);renamed=[]
    for text,expected in result:
        names={f'v{i}':f'v{r}' for i,r in enumerate(rng.sample(range(20,900),10))}
        text=re.sub(r'\bv\d+\b',lambda m:names[m[0]],text)
        lines=text.splitlines();parts=[]
        for line in lines[1:]:
            if line.endswith(':'):parts.append([line])
            else:parts[-1].append(line)
        rest=parts[1:];rng.shuffle(rest)
        renamed.append((lines[0]+'\n'+'\n'.join(line for part in [parts[0],*rest] for line in part)+'\n',expected))
    return renamed


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('kit',type=Path);args=parser.parse_args()
    kit=args.kit.resolve();sys.dont_write_bytecode=True
    sys.path.insert(0,str(kit));sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    import kirlib as ref
    from src.groups import group
    from src.kirlib import parse_program
    from src.optimizer import optimize
    default=ref.load_machine(kit/'machines/machine_default.cfg')
    machines={p.stem:ref.load_machine(p) for p in sorted((kit/'machines').glob('*.cfg'))}
    machines.update({name:default|values for name,values in MACHINE_VARIANTS.items()})
    rng=random.Random(864193);outcomes=Counter();comparisons=accepted=0
    values=[(n,(0,1,0xFFFFFFFF,0x80000000)[n%4]) for n in range(33)]
    patterns=[[0]*4096,[0xFFFFFFFF]*4096,[0x7FFFFFFF,0x80000000]*2048,[rng.getrandbits(32) for _ in range(4096)]]
    inputs=[(list(value),[(0,patterns[i%4])],{7:[0,1,0xFFFFFFFF,0x80000000]}) for i,value in enumerate(values)]
    with tempfile.TemporaryDirectory(prefix='oxygen-groups-') as folder:
        work=Path(folder);inp=work/'in.kir';out=work/'out.kir'
        for name,mc in machines.items():(work/f'{name}.cfg').write_text(''.join(f'{k} = {v}\n' for k,v in mc.items()))
        for index,(text,expected) in enumerate(fixtures()):
            inp.write_text(text);original=ref.compile_program(ref.load_program(inp))
            references=[ref.execute(original,*data,100000) for data in inputs]
            valid=[(data,before) for data,before in zip(inputs,references) if before.status!='TIMEOUT']
            if len(valid)!=len(inputs):raise RuntimeError(f'unexpected timeout {index}')
            grouped=[]
            for factor in (2,4,8):
                for placement in ('tail','group','original'):
                    candidate=group(parse_program(text),factor,placement,require_minimum=False)
                    if (candidate is not None)!=expected:raise RuntimeError(f'proof expectation {index}, U={factor}, {placement}, {expected}\n{text}')
                    if candidate is not None:grouped.append(candidate)
            accepted+=expected
            for name,mc in machines.items():
                variants=[]
                for candidate in grouped:
                    out.write_text(candidate);variants.append(ref.compile_program(ref.load_program(out)))
                    cleaned=optimize(parse_program(candidate),candidate,mc)
                    out.write_text(cleaned or candidate);parsed=ref.load_program(out);ref.check_machine_features(parsed,mc)
                    variants.append(ref.compile_program(parsed))
                result=subprocess.run([Path(__file__).resolve().parents[1]/'kopt',inp,'--machine',work/f'{name}.cfg','-o',out],capture_output=True,timeout=5)
                if result.returncode:raise RuntimeError(result.stderr.decode())
                parsed=ref.load_program(out);ref.check_machine_features(parsed,mc);variants.append(ref.compile_program(parsed))
                for data,before in valid:
                    for compiled in variants:
                        after=ref.execute(compiled,*data,100000)
                        difference=ref.first_difference(before,after)
                        if difference:raise RuntimeError(f'{index}, {name}, {data[0]}: {difference}\n{text}')
                        comparisons+=1
                    outcomes[before.status if before.status=='RET' else before.value]+=1
    print(f'{len(fixtures())} counted-group fixtures, {accepted} accepted, factors 2/4/8 × 3 placements, {len(machines)} machines: '
          f'{comparisons:,} direct/cleaned/CLI matches; {dict(outcomes)}; 0 reference timeouts')


if __name__=='__main__':main()
