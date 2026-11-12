"""Independent direct/unselected/CLI checks for control and induction proofs."""

import argparse
from collections import Counter
from pathlib import Path
import random
import subprocess
import sys
import tempfile

from stress import MACHINE_VARIANTS


def diamond(yes=1,no=-1,variant='plain'):
    left=[f'add v4, v1, {yes}', 'mov v3, v4']
    right=[f'add v5, v1, {no}', 'mov v3, v5']
    done=['store 200, v3','ret v3']
    if variant=='self':left=[f'add v0, v0, {yes}'];right=[f'add v0, v0, {no}'];done=['ret v0']
    if variant=='chain':left=['add v4, v1, 3',f'sub v3, v4, {3-yes}'];right=['sub v5, v1, 7',f'add v3, v5, {no+7}']
    if variant=='leak':done=['add v3, v3, v4','ret v3']
    if variant=='cross_carry':left=['add v4, v4, 1','mov v3, v4'];right=['add v3, v4, 2']
    if variant=='effect':left=['store 200, v1','add v3, v1, 1']
    if variant=='load':left=['load v3, v1']
    if variant=='division':left=['div v3, v1, 2']
    if variant=='nonlinear':left=['xor v3, v1, 1']
    blocks={'entry':['store 700, v1','br v0, yes, no'],'yes':left+['jmp done'],'no':right+['jmp done'],'done':done}
    if variant=='shared':blocks['other']=['jmp yes']
    return render(blocks)


def guarded(limit=17,variant='plain',mask=255):
    setup=[f'and v1, v0, {mask}','const v2, 0','const v3, 0','store 700, v1','jmp head']
    if variant=='signed':setup[0]='mov v1, v0'
    if variant=='initial':setup[1]='const v2, -1'
    check=[f'lt v5, v2, {limit}','br v5, body, trap']
    if variant=='negated':check=[f'lt v5, v2, {limit}','eq v6, v5, 0','br v6, trap, body']
    if variant=='guard_effect':check.insert(0,'store 701, v2')
    body=['add v7, 300, v2','store v7, v3','load v8, v2','add v3, v3, v8','add v9, v2, 1','mov v2, v9','jmp head']
    if variant=='early_trap':body[2]='load v8, 4096'
    if variant=='volatile':body[2:2]=['vload v10, 7','vstore 8, v10']
    if variant=='stride':body[-3]='add v9, v2, 2'
    if variant=='mutable_bound':body.insert(0,'const v1, 0')
    done=['add v3, v3, v4','ret v3']
    if variant=='live_guard':done=['add v3, v3, v5','ret v3']
    trap=['vstore 9, v4','store 701, v4','trap v4'] if variant=='live_condition' else ['trap 7']
    return render({'entry':setup,'head':['lt v4, v2, v1','br v4, guard, done'],
                   'guard':check,'body':body,'trap':trap,'done':done})


def pointer(offset=512,variant='plain'):
    setup=['and v2, v0, 63','add v2, v2, 2','and v3, v1, 15','and v4, v1, 3','add v4, v4, 1',
           'mov v5, v1','store 700, v0','jmp head']
    body=[f'add v7, v3, {offset}','load v8, v7','add v5, v5, v8','store v7, v5','add v9, v3, v4','mov v3, v9','jmp head']
    done=['ret v5']
    if variant=='live_index':done=['add v5, v5, v3','ret v5']
    if variant=='live_address':done=['add v5, v5, v7','ret v5']
    if variant=='carry_temp':body.insert(1,'add v5, v5, v9')
    if variant=='counter_data':body.insert(1,'add v5, v5, v3')
    if variant=='mutable_bound':body.insert(1,'const v2, 0')
    if variant=='mutable_step':body.insert(1,'const v4, 2')
    if variant=='zero_step':setup[4]='const v4, 0';body[1]='load v8, 4096'
    if variant=='negative_step':setup[4]='const v4, -1';body[1]='load v8, 4096'
    if variant=='wide_start':setup[2]='and v3, v1, 2147483647'
    if variant=='predicate_step':body[-3]='add v9, v3, v6'
    if variant=='same_bound':setup[0]='const v2, 0'
    if variant=='volatile':body[2:2]=['vload v10, 7','vstore 8, v10']
    if variant=='inplace':body[-3:-1]=['add v3, v3, v4']
    bound='v3' if variant=='same_bound' else 'v2'
    return render({'entry':setup,'head':[f'lt v6, v3, {bound}','br v6, body, done'],'body':body,'done':done})


def render(blocks):
    return 'func generated(v0, v1)\n'+''.join(label+':\n  '+'\n  '.join(items)+'\n' for label,items in blocks.items())


def fixtures():
    result=[]
    for yes,no in ((1,-1),(0,7),(2147483647,-2147483648),(-17,81)):
        for variant in ('plain','self','chain'):result.append(('diamonds',diamond(yes,no,variant),True))
    for variant in ('leak','cross_carry','effect','load','division','nonlinear','shared'):
        result.append(('diamonds',diamond(variant=variant),False))
    for limit in (0,1,3,17,64,128):
        for variant in ('plain','negated','signed','live_condition','early_trap','volatile'):
            result.append(('guards',guarded(limit,variant),True))
    for variant in ('initial','stride','mutable_bound','guard_effect','live_guard'):
        result.append(('guards',guarded(variant=variant),False))
    result.append(('guards',guarded(4097),False))
    # CFG predecessors do not include the implicit function-entry edge.
    text=guarded();parts=text.split('body:\n',1)
    body,remaining=parts[1].split('trap:\n',1)
    result.append(('guards',text.splitlines()[0]+'\nbody:\n'+body+
                   '\n'.join(parts[0].splitlines()[1:])+'\ntrap:\n'+remaining,False))
    for offset in (-3,0,512,3070,4090):
        for variant in ('plain','volatile','inplace'):result.append(('pointers',pointer(offset,variant),True))
    for variant in ('live_index','live_address','carry_temp','counter_data','mutable_bound','mutable_step',
                    'zero_step','negative_step','wide_start','predicate_step','same_bound'):
        result.append(('pointers',pointer(variant=variant),False))
    result.append(('pointers',pointer(2147483647),False))
    for mode,text,expected in list(result):
        if mode=='pointers':
            result.append(('unroll',text,'lt v6, v3, v3' not in text))
    # Renaming and block layout must never supply a semantic fact.
    rng=random.Random(715289);shuffled=[]
    import re
    for mode,text,expected in result:
        mapping={f'v{i}':f'v{n}' for i,n in enumerate(rng.sample(range(20,900),11))}
        # Keep parameter identity/order through the same alpha-renaming.
        text=re.sub(r'\bv\d+\b',lambda match:mapping.get(match[0],match[0]),text)
        lines=text.splitlines();parts=[];current=[]
        for line in lines[1:]:
            if line.endswith(':'):
                if current:parts.append(current)
                current=[line]
            else:current.append(line)
        parts.append(current);rest=parts[1:];rng.shuffle(rest)
        shuffled.append((mode,lines[0]+'\n'+'\n'.join(line for part in [parts[0],*rest] for line in part)+'\n',expected))
    return shuffled


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('kit',type=Path);args=parser.parse_args()
    sys.dont_write_bytecode=True;kit=args.kit.resolve()
    sys.path.insert(0,str(kit));sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    import kirlib as ref
    from src.control import rewrite
    from src.kirlib import parse_program
    from src.optimizer import optimize
    default=ref.load_machine(kit/'machines/machine_default.cfg')
    machines={p.stem:ref.load_machine(p) for p in sorted((kit/'machines').glob('*.cfg'))}
    machines.update({name:default|values for name,values in MACHINE_VARIANTS.items()})
    rng=random.Random(918274);comparisons=skipped=0;accepted=Counter();outcomes=Counter()
    edges=(0,1,2,3,16,17,18,63,64,65,127,128,255,0x7FFFFFFF,0x80000000,0xFFFFFFFF)
    inputs=[([edge,edges[(i+5)%16]],[(0,[rng.getrandbits(32) for _ in range(4096)])],{7:[0,1,0xFFFFFFFF,0x80000000]}) for i,edge in enumerate(edges)]
    with tempfile.TemporaryDirectory(prefix='oxygen-control-') as folder:
        work=Path(folder);source=work/'in.kir';output=work/'out.kir'
        for name,mc in machines.items():(work/f'{name}.cfg').write_text(''.join(f'{k} = {v}\n' for k,v in mc.items()))
        for index,(mode,text,expected) in enumerate(fixtures()):
            source.write_text(text);original=ref.compile_program(ref.load_program(source))
            transformed=rewrite(parse_program(text),mode)
            if (transformed is not None)!=expected:raise RuntimeError(f'proof expectation {index}, {mode}, {expected}\n{text}')
            accepted[mode]+=transformed is not None
            output.write_text(transformed or text);direct=ref.compile_program(ref.load_program(output))
            references=[ref.execute(original,*data,100000) for data in inputs]
            if any(before.status=='TIMEOUT' for before in references):raise RuntimeError(f'unexpected reference timeout {index}')
            for name,mc in machines.items():
                unselected_source=optimize(parse_program(transformed or text),transformed or text,mc)
                output.write_text(unselected_source or transformed or text)
                parsed=ref.load_program(output);ref.check_machine_features(parsed,mc);unselected=ref.compile_program(parsed)
                variants=[('direct',direct),('unselected',unselected)]
                if transformed is not None and mode in ('guards','pointers'):
                    unrolled=rewrite(parse_program(transformed),'unroll')
                    if unrolled is None:raise RuntimeError('missing composed unroll')
                    output.write_text(unrolled);variants.append(('composed',ref.compile_program(ref.load_program(output))))
                    cleaned=optimize(parse_program(unrolled),unrolled,mc)
                    output.write_text(cleaned or unrolled);parsed=ref.load_program(output);ref.check_machine_features(parsed,mc)
                    variants.append(('composed-unselected',ref.compile_program(parsed)))
                run=subprocess.run([Path(__file__).resolve().parents[1]/'kopt',source,'--machine',work/f'{name}.cfg','-o',output],capture_output=True,timeout=5)
                if run.returncode:raise RuntimeError(run.stderr.decode())
                parsed=ref.load_program(output);ref.check_machine_features(parsed,mc);selected=ref.compile_program(parsed)
                for data,before in zip(inputs,references):
                    for kind,compiled in [*variants,('selected',selected)]:
                        after=ref.execute(compiled,*data,100000)
                        difference=ref.first_difference(before,after)
                        if difference:raise RuntimeError(f'{index}, {mode}, {name}, {data[0]}, {kind}: {difference}\n{text}')
                        comparisons+=1
                    outcomes[before.status if before.status=='RET' else before.value]+=1
    print(f'{len(fixtures())} renamed/shuffled control fixtures × {len(machines)} machines × 16 inputs: '
          f'{comparisons:,} direct/composed/unselected/selected matches; proved {dict(accepted)}; {dict(outcomes)}; {skipped} reference timeouts')


if __name__=='__main__':main()
