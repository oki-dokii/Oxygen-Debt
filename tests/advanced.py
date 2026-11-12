"""Independent checks for bit synthesis, nested LICM and wider finite proofs."""
import argparse
from collections import Counter
from pathlib import Path
import random
import subprocess
import sys
import tempfile
from stress import MACHINE_VARIANTS


def bit_source(kind, width, polynomial=0xEDB88320):
    setup = '  mov v2, v0\n  const v3, 0\n  const v4, 0\n  jmp head\n'
    header = f'head:\n  lt v5, v4, {width}\n  br v5, body, done\n'
    if kind == 'pop':
        body = 'body:\n  shr v6, v2, v4\n  and v6, v6, 1\n  add v3, v3, v6\n  add v4, v4, 1\n  jmp head\n'
        ret = 'v3'
    elif kind == 'reverse':
        body = f'body:\n  shr v6, v2, v4\n  and v6, v6, 1\n  sub v7, {width-1}, v4\n  shl v6, v6, v7\n  or v3, v3, v6\n  add v4, v4, 1\n  jmp head\n'
        ret = 'v3'
    else:
        body = ('body:\n  and v6, v2, 1\n  eq v7, v6, 1\n  br v7, yes, no\n'
                f'yes:\n  shr v2, v2, 1\n  xor v2, v2, {polynomial}\n  jmp latch\n'
                'no:\n  shr v2, v2, 1\n  jmp latch\nlatch:\n  add v4, v4, 1\n  jmp head\n')
        ret = 'v2'
    return 'func generated(v0, v1)\nentry:\n'+setup+header+body+f'done:\n  xor v9, {ret}, v1\n  ret v9\n'


def nested_source(observed=False):
    return ('func generated(v0, v1)\nentry:\n  and v0, v0, 3\n  const v2, 9\n  const v3, 0\n  const v8, 7\n  jmp h\n'
            'h:\n  lt v4, v3, v0\n  br v4, outer, done\nouter:\n  const v5, 0\n  jmp inner\n'
            'inner:\n  lt v6, v5, 2\n  br v6, body, end\nbody:\n  mul v8, v1, 3\n'
            '  add v2, v2, v8\n  add v5, v5, 1\n  jmp inner\nend:\n  add v3, v3, 1\n  jmp h\n'
            + ('done:\n  ret v8\n' if observed else 'done:\n  store 0, v2\n  ret v2\n'))


def linear_source(inner,coefficient,outer,offset,initial,mask):
    setup='  mov v2, v1' if initial is None else f'  const v2, {initial}'
    return ('func generated(v0, v1)\nentry:\n'+f'  and v0, v0, {mask}\n'+setup+'\n  const v3, 0\n  jmp h\n'
            'h:\n  lt v4, v3, v0\n  br v4, outer, done\nouter:\n  const v5, 0\n  jmp inner\n'
            f'inner:\n  lt v6, v5, {inner}\n  br v6, body, end\nbody:\n  mul v8, v1, {coefficient}\n'
            f'  mul v9, v3, {outer}\n  add v8, v8, v9\n  add v8, v8, v5\n  add v8, v8, {offset}\n'
            '  add v2, v2, v8\n  add v5, v5, 1\n  jmp inner\nend:\n  add v3, v3, 1\n  jmp h\ndone:\n  store 0, v2\n  ret v2\n')


def main():
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('kit',type=Path); args=parser.parse_args()
    kit=args.kit.resolve();sys.dont_write_bytecode=True
    sys.path.insert(0,str(kit));sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    import kirlib as ref
    from src.bitloops import synthesize
    from src.finite import masked_parameter
    from src.optimizer import PURE, render_canonical
    from src.nested import hoist_nested
    rng=random.Random(638193)
    machines={p.stem:ref.load_machine(p) for p in sorted((kit/'machines').glob('*.cfg'))}
    default=ref.load_machine(kit/'machines/machine_default.cfg')
    machines.update({k:default|v for k,v in MACHINE_VARIANTS.items()})
    fixtures=[(bit_source(kind,width),kind,width,0) for kind in ('pop','reverse') for width in (1,7,16,31,32)]
    fixtures += [(bit_source('crc',width,poly),'crc',width,poly) for width in (1,4,8)
                 for poly in (0,0x1D,0xA001,0xEDB88320,0xFFFFFFFF)]
    fixtures += [(nested_source(False),'nested',0,0),(nested_source(True),'observed',0,0)]
    # Twelve relevant masked bits, including two input words; output classes collapse.
    for two in (False,True):
        prefix='  and v2, v0, 63\n  and v3, v1, 63\n  xor v2, v2, v3\n' if two else '  and v2, v0, 4095\n'
        text='func generated(v0, v1)\nentry:\n'+prefix
        text+='  mul v2, v2, 17\n  xor v2, v2, 3\n'*12+'  and v2, v2, 7\n  ret v2\n'
        fixtures.append((text,'finite',0,0))
    fixtures += [(bit_source('pop',8).replace('  add v4, v4, 1','  add v4, v4, 2'),'reject',0,0),
                 (bit_source('reverse',8).replace('  or v3, v3, v6','  vstore 7, v6\n  or v3, v3, v6'),'reject',0,0),
                 (bit_source('crc',8).replace('  xor v2, v2, 3988292384','  mul v2, v2, v1'),'reject',0,0)]
    for index in range(10):
        settings=dict(inner=(0,1,2,7,16)[index%5],coefficient=(3,-3,0,17)[index%4],
                      outer=(5,-7)[index%2],offset=index-4,initial=None if index%3==0 else 9,mask=(3,7,15)[index%3])
        fixtures.append((linear_source(**settings),'linear',0,settings))
    totals=Counter(); selected=Counter(); comparisons=0
    with tempfile.TemporaryDirectory(prefix='oxygen-advanced-') as folder:
        work=Path(folder); inp=work/'in.kir';out=work/'out.kir'
        for name,mc in machines.items(): (work/f'{name}.cfg').write_text(''.join(f'{k} = {v}\n' for k,v in mc.items()))
        for index,(text,kind,width,poly) in enumerate(fixtures):
            inp.write_text(text);original=ref.compile_program(ref.load_program(inp))
            words=[0,1,2,3,0x7FFFFFFF,0x80000000,0xFFFFFFFF,*[rng.getrandbits(32) for _ in range(25)]]
            values=[[word,words[-i-1]] for i,word in enumerate(words)]
            references=[ref.execute(original,v,[(0,[17,19])],{7:[11]},10000) for v in values]
            for v,run in zip(values,references):
                x,y=v
                if kind=='pop': expected=(x&((1<<width)-1)).bit_count()^y
                elif kind=='reverse': expected=int(f'{x&((1<<width)-1):0{width}b}'[::-1],2)^y
                elif kind=='crc':
                    expected=x
                    for _ in range(width): expected=(expected>>1)^(poly if expected&1 else 0)
                    expected ^= y
                elif kind=='linear':
                    expected=y if poly['initial'] is None else poly['initial']
                    for outer in range(x&poly['mask']):
                        for inner in range(poly['inner']):
                            expected += poly['coefficient']*y+poly['outer']*outer+inner+poly['offset']
                    expected &= 0xFFFFFFFF
                elif kind=='nested': expected=(9+6*(x&3)*y)&0xFFFFFFFF
                elif kind=='observed': expected=7 if not x&3 else 3*y&0xFFFFFFFF
                else: continue
                if run.status!='RET' or run.value!=expected: raise RuntimeError(f'oracle disagreement: {kind}, {v}')
            from src.kirlib import parse_program
            program=parse_program(text);starts=[program.labels[k] for k in program.block_labels]
            blocks={label:program.instrs[a:b] for label,a,b in zip(program.block_labels,starts,[*starts[1:],len(program.instrs)])}
            if kind in ('pop','reverse','crc','reject'):
                proof=synthesize(blocks,PURE)
                if kind=='reject' and proof is not None: raise RuntimeError('unsafe bit proof accepted')
                if kind!='reject' and proof is None: raise RuntimeError(f'missing bit proof: {kind} {width} {poly}')
                selected[kind]+=proof is not None
                if proof is not None:
                    # Retain only reachable blocks after changing the preheader edge.
                    reachable=set();pending=[program.block_labels[0]]
                    while pending:
                        label=pending.pop()
                        if label in reachable:continue
                        reachable.add(label);pending.extend(v for k,v in blocks[label][-1].args if k=='l')
                    kept={k:v for k,v in blocks.items() if k in reachable}
                    out.write_text(render_canonical(program,kept,list(kept),{}))
                    direct=ref.compile_program(ref.load_program(out))
                    for v,before in zip(values,references):
                        after=ref.execute(direct,v,[(0,[17,19])],{7:[11]},10000)
                        if ref.first_difference(before,after):raise RuntimeError(f'direct bit mismatch {index} {v}')
                        comparisons+=1
            if kind=='finite' and len(masked_parameter(program) or [])!=12: raise RuntimeError('missing twelve-bit proof')
            if kind in ('nested','observed'):
                hoist_nested(blocks,PURE)
                if kind=='observed' and not any(ins.op=='mul' for ins in blocks['body']):raise RuntimeError('zero-trip observable was hoisted')
                out.write_text(render_canonical(program,blocks,program.block_labels,{}));direct=ref.compile_program(ref.load_program(out))
                for v,before in zip(values,references):
                    after=ref.execute(direct,v,[(0,[17,19])],{7:[11]},10000)
                    if ref.first_difference(before,after):raise RuntimeError('nested hoist mismatch')
                    comparisons+=1
            for name,mc in machines.items():
                subprocess.run([Path(__file__).resolve().parents[1]/'kopt',inp,'--machine',work/f'{name}.cfg','-o',out],check=True,capture_output=True,timeout=5)
                if kind in ('linear','nested','observed'):
                    from src.optimizer import optimize
                    candidate=optimize(parse_program(text),text,mc,{},frozenset({'nested'}))
                    if candidate is not None:
                        candidate_path=work/'nested.kir';candidate_path.write_text(candidate)
                        emitted=ref.compile_program(ref.load_program(candidate_path))
                        for v,before in zip(values,references):
                            after=ref.execute(emitted,v,[(0,[17,19])],{7:[11]},10000)
                            if ref.first_difference(before,after):raise RuntimeError(f'unselected nested candidate mismatch {index} {name} {v}')
                            comparisons+=1
                parsed=ref.load_program(out);ref.check_machine_features(parsed,mc);compiled=ref.compile_program(parsed)
                for v,before in zip(values,references):
                    after=ref.execute(compiled,v,[(0,[17,19])],{7:[11]},10000)
                    difference=ref.first_difference(before,after)
                    if difference:raise RuntimeError(f'advanced {index} {name} {v}: {difference}\n{text}')
                    comparisons+=1;totals[kind]+=1
    print(f'{len(fixtures)} advanced fixtures, {comparisons:,} comparisons; bit proofs {dict(selected)}; {dict(totals)}')

if __name__=='__main__':main()
