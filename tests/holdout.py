"""Fresh larger matrices and array loops on unseen machines and bad profiles.

The fixed seed is separate from compiler timing inputs and existing suites.
An optional frozen optimizer supplies performance comparisons, never proof facts.
"""

import argparse
from collections import Counter, defaultdict
import json
import os
from pathlib import Path
import random
import re
import subprocess
import sys
import tempfile
import time

from expansion import matrix


SEED=451729


def stream(base,delta,variant,mask=127,minimum=0):
    setup=[f'and v3, v0, {mask}','and v4, v1, 3','and v5, v1, 7','add v5, v5, 1',
           'mov v6, v2','const v11, 0','store 702, v0','vstore 17, v2','jmp head']
    if variant=='signed':setup[0]='mov v3, v0'
    if variant=='guard':setup[1:4]=['const v4, 0','const v5, 1']
    if minimum:setup.insert(1,f'add v3, v3, {minimum}')
    body=[f'add v8, v4, {base}','load v9, v8','xor v6, v6, v9',f'add v10, v8, {delta}',
          'store v10, v6']
    if variant=='alias':body[-1]='store v2, v6'
    if variant=='volatile':body+=['vload v11, 17','vstore 18, v11','add v6, v6, v11']
    if variant=='division':body+=['div v6, v6, v2']
    body+=['add v12, v4, 1' if variant=='guard' else 'add v12, v4, v5','mov v4, v12','jmp head']
    target='guard' if variant=='guard' else 'body'
    blocks={'entry':setup,'head':['lt v7, v4, v3',f'br v7, {target}, done'],'body':body,
            'done':['add v6, v6, v4','xor v6, v6, v7','xor v6, v6, v11','ret v6']}
    if variant=='guard':blocks.update({'guard':['lt v13, v4, 37','br v13, body, trap'],'trap':['vstore 19, v7','trap v7']})
    return 'func held(v0, v1, v2)\n'+''.join(label+':\n  '+'\n  '.join(items)+'\n' for label,items in blocks.items())


def fixtures(seed=SEED):
    rng=random.Random(seed);result=[]
    dimensions=((8,8,8),(16,16,16),(3,11,7),(7,2,13),(2,9,5),(5,0,3),(0,5,4),(4,3,0),(1,16,16),(16,1,8))
    for rows,cols,depth in dimensions:
        for a,b,c in ((0,512,1536),(0,128,0),(3070,512,4090)):
            settings=dict(rows=rows,cols=cols,depth=depth,a=a,b=b,c=c)
            result.append(('matrix',matrix(rng,**settings),settings))
    for base,delta in ((0,0),(5,-1),(3070,3),(4090,129),(-5,1)):
        for variant in ('plain','volatile','alias','division','guard'):
            result.append(('stream',stream(base,delta,variant,0x7FFFFFFF if variant=='guard' else 127),{}))
    for base,delta in ((0,0),(5,-1),(3070,3),(4090,129),(-5,1)):
        result.append(('stream',stream(base,delta,'signed'),{}))
    for base,delta in ((0,0),(5,-1),(3070,3),(4090,129)):
        for variant in ('plain','volatile','alias','division'):
            result.append(('long_stream',stream(base,delta,variant,63,128),{}))
    # Different register identities and physical block orders from the proof suite.
    renamed=[]
    for family,text,settings in result:
        used=sorted(set(re.findall(r'\bv\d+\b',text)),key=lambda value:int(value[1:]))
        names=dict(zip(used,[f'v{r}' for r in rng.sample(range(50,950),len(used))]))
        text=re.sub(r'\bv\d+\b',lambda match:names[match[0]],text)
        lines=text.splitlines();parts=[]
        for line in lines[1:]:
            if line.endswith(':'):parts.append([line])
            else:parts[-1].append(line)
        rest=parts[1:];rng.shuffle(rest)
        renamed.append((family,lines[0]+'\n'+'\n'.join(line for part in [parts[0],*rest] for line in part)+'\n',settings))
    return renamed


def machines(default,seed=SEED):
    rng=random.Random(seed+1);result={}
    for index,registers in enumerate((4,5,7,11,19,31)):
        mc=default|dict(registers=registers,issue_width=(1,2,3,4,6,8)[index],mem_ports=(1,1,2,1,3,4)[index],
            reg_spill_penalty=(23,0,11,3,31,1)[index],taken_branch_penalty=(0,37,1,13,4,29)[index],
            icache_size=(1,17,37,127,257,4096)[index],icache_penalty=(0,7,1,3,0,2)[index],
            lat_alu=rng.randint(1,7),lat_mul=rng.randint(1,17),lat_div=rng.randint(1,31),
            lat_load=rng.randint(1,41),lat_mac=rng.randint(1,17),lat_addsh=rng.randint(1,11),
            fused_mac=index%2,fused_addsh=(index//2)%2)
        result[f'unseen_{registers}']=mc
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('kit',type=Path)
    parser.add_argument('--baseline',type=Path);parser.add_argument('--report',type=Path)
    parser.add_argument('--seed',type=int,default=SEED)
    parser.add_argument('--artifacts',type=Path,default=Path('/tmp/oxygen-holdout-failure'))
    args=parser.parse_args();sys.dont_write_bytecode=True;kit=args.kit.resolve()
    sys.path.insert(0,str(kit));import kirlib as ref
    repo=Path(__file__).resolve().parents[1];rng=random.Random(args.seed+2)
    configs=machines(ref.load_machine(kit/'machines/machine_default.cfg'),args.seed)
    patterns=[[0]*4096,[0xFFFFFFFF]*4096,[0x80000000,0x7FFFFFFF,0,1]*1024,
              [rng.getrandbits(32) if i%13==0 else 0 for i in range(4096)],
              [rng.getrandbits(32) for _ in range(4096)]]
    words=(0,1,3,4,7,8,9,15,31,32,33,63,64,65,127,0xFFFFFFFF,0x80000000)
    count=oracles=0;outcomes=Counter();perf=Counter();totals=defaultdict(lambda:[0,0]);maximum=[0.0,0.0]
    worst_ratio=None;worst_extra=None
    with tempfile.TemporaryDirectory(prefix='oxygen-holdout-') as folder:
        work=Path(folder);source=work/'held.kir';output=work/'out.kir';profile=work/'wrong.prof'
        for name,mc in configs.items():(work/f'{name}.cfg').write_text(''.join(f'{k} = {v}\n' for k,v in mc.items()))
        for index,(family,text,settings) in enumerate(fixtures(args.seed)):
            source.write_text(text);parsed=ref.load_program(source);original=ref.compile_program(parsed)
            profile.write_text(''.join(f'edge {owner} {target} {10**15 if j else 1}\n'
                for ins,owner in zip(parsed.instrs,parsed.block_of) if ins.op=='br'
                for j,(_,target) in enumerate(ins.args[1:]))+'edge absent nowhere 999999999999999999\n')
            def fail(message,data=None,machine=None):
                args.artifacts.mkdir(parents=True,exist_ok=True)
                (args.artifacts/'source.kir').write_text(text)
                (args.artifacts/'profile.prof').write_bytes(profile.read_bytes())
                if output.exists():(args.artifacts/'output.kir').write_bytes(output.read_bytes())
                if machine:(args.artifacts/'machine.cfg').write_bytes((work/f'{machine}.cfg').read_bytes())
                (args.artifacts/'failure.json').write_text(json.dumps(dict(seed=args.seed,index=index,family=family,
                    settings=settings,machine=machine,message=message,input=data),indent=2))
                raise RuntimeError(f'{message}; saved {args.artifacts}')
            inputs=[]
            for i in range(10):
                argv=[words[(i*3+p*5+index)%len(words)] for p in range(len(parsed.params))]
                inputs.append((argv,[(0,patterns[(i+index)%len(patterns)])],{17:[0,0xFFFFFFFF,1,0x80000000]}))
            references=[ref.execute(original,*data,1000000,want_trace=True) for data in inputs]
            for data,run in zip(inputs,references):
                if run.status=='TIMEOUT':fail(f'reference timeout {index}',data)
            if family=='matrix':
                for data,run in zip(inputs,references):
                    if run.status!='RET':continue
                    memory=data[1][0][1].copy();memory[700]=data[0][0]
                    rows,cols,depth=(settings[key] for key in ('rows','cols','depth'))
                    for i in range(rows):
                        for j in range(cols):
                            total=data[0][0]
                            for k in range(depth):
                                total=(total+memory[settings['a']+i*depth+k]*memory[settings['b']+k*cols+j])&0xFFFFFFFF
                            memory[settings['c']+i*cols+j]=total
                    expected=(memory[settings['c']]+rows+(cols if rows else 0)+(depth if rows and cols else 0))&0xFFFFFFFF
                    if run.value!=expected or run.mem[:3072]!=memory[:3072]:fail(f'matrix oracle {index}',data)
                    oracles+=1
            for name,mc in configs.items():
                option=['--profile',profile] if index%3 else []
                blobs=[]
                for seed in ('13','975318642'):
                    started=time.monotonic()
                    try:
                        result=subprocess.run([repo/'kopt',source,'--machine',work/f'{name}.cfg',*option,'-o',output],
                            capture_output=True,timeout=5,env=os.environ|{'PYTHONHASHSEED':seed})
                    except subprocess.TimeoutExpired:fail(f'current compiler timeout {index}',machine=name)
                    maximum[0]=max(maximum[0],time.monotonic()-started)
                    if result.returncode:fail(result.stderr.decode(),machine=name)
                    blobs.append(output.read_bytes())
                if blobs[0]!=blobs[1]:fail(f'hash nondeterminism {index}, {name}',machine=name)
                new=ref.load_program(output);ref.check_machine_features(new,mc);new=ref.compile_program(new)
                baseline=None
                if args.baseline:
                    old_path=work/'baseline.kir';started=time.monotonic()
                    try:
                        result=subprocess.run([args.baseline.resolve(),source,'--machine',work/f'{name}.cfg',*option,'-o',old_path],
                                              capture_output=True,timeout=5)
                    except subprocess.TimeoutExpired:fail(f'frozen compiler timeout {index}',machine=name)
                    maximum[1]=max(maximum[1],time.monotonic()-started)
                    if result.returncode:fail('frozen compiler: '+result.stderr.decode(),machine=name)
                    baseline=ref.compile_program(ref.load_program(old_path))
                for data,before in zip(inputs,references):
                    after=ref.execute(new,*data,1000000,want_trace=True)
                    difference=ref.first_difference(before,after)
                    if difference:
                        fail(f'holdout {index}, {name}: {difference}',data,name)
                    count+=1;outcomes[before.status if before.status=='RET' else before.value]+=1
                    if baseline:
                        old=ref.execute(baseline,*data,1000000,want_trace=True)
                        difference=ref.first_difference(before,old)
                        if difference:fail(f'frozen baseline failure {index}, {name}: {difference}',data,name)
                        a,b=ref.time_trace(baseline,old.trace,mc),ref.time_trace(new,after.trace,mc)
                        totals[family][0]+=a;totals[family][1]+=b
                        perf['faster' if b<a else 'slower' if b>a else 'tied']+=1
                        if b>a:
                            detail=dict(case=index,family=family,machine=name,input=data[0],before=a,after=b,
                                        extra_cycles=b-a,ratio=b/a)
                            if worst_ratio is None or b*worst_ratio['before']>worst_ratio['after']*a:worst_ratio=detail
                            if worst_extra is None or b-a>worst_extra['extra_cycles']:worst_extra=detail
    report=dict(seed=args.seed,fixtures=len(fixtures(args.seed)),machines=len(configs),inputs=10,matches=count,
                matrix_oracles=oracles,reference_timeouts=0,outcomes=dict(outcomes),performance=dict(perf),
                cycles=dict(totals),max_current_seconds=maximum[0],max_baseline_seconds=maximum[1],
                baseline=str(args.baseline) if args.baseline else None,worst_slowdown=worst_ratio,worst_extra_cycles=worst_extra)
    if args.report:args.report.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,sort_keys=True))


if __name__=='__main__':main()
