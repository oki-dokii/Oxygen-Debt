"""Independent checks of static-control expansion, including unselected output."""

import argparse
from collections import Counter
from pathlib import Path
import random
import subprocess
import sys
import tempfile

from stress import MACHINE_VARIANTS


def matrix(rng, rows=3, cols=3, depth=3, a=0, b=32, c=64, variant="plain"):
    names = [f"v{r}" for r in rng.sample(range(10, 900), 13)]
    i,j,k,test,total,addr,x,y,product,tmp,output,zero,unused = names
    labels = [f"node_{n}_{rng.randrange(100000)}" for n in range(10)]
    entry, rh, rb, ch, cb, kh, kb, ke, ce, done = labels
    inner = [f"mul {addr}, {i}, {depth}", f"add {addr}, {addr}, {k}", f"add {addr}, {addr}, {a}",
             f"load {x}, {addr}", f"mul {addr}, {k}, {cols}", f"add {addr}, {addr}, {j}",
             f"add {addr}, {addr}, {b}", f"load {y}, {addr}", f"mul {product}, {x}, {y}",
             f"add {total}, {total}, {product}"]
    if variant == "volatile": inner += [f"vload {x}, 7", f"vstore 9, {x}", f"add {total}, {total}, {x}"]
    if variant == "unknown_address": inner += [f"load {x}, {addr}", f"store v0, {total}", f"load {x}, v1", f"add {total}, {total}, {x}"]
    if variant == "divide": inner += [f"div {total}, {total}, v1"]
    if variant == "unknown_branch": inner += [f"br {x}, {ke}, {kh}"]
    else: inner += [f"add {k}, {k}, 1", f"jmp {kh}"]
    blocks = {
        entry: [f"const {i}, 0", f"store 700, v0", f"jmp {rh}"],
        rh: [f"lt {test}, {i}, {rows}", f"br {test}, {rb}, {done}"],
        rb: [f"const {j}, 0", f"jmp {ch}"],
        ch: [f"lt {test}, {j}, {cols}", f"br {test}, {cb}, {ce}"],
        cb: [f"mov {total}, v0", f"const {k}, 0", f"jmp {kh}"],
        kh: [f"lt {test}, {k}, {depth}", f"br {test}, {kb}, {ke}"],
        kb: inner,
        ke: [f"mul {addr}, {i}, {cols}", f"add {addr}, {addr}, {j}", f"add {addr}, {addr}, {c}",
             f"store {addr}, {total}", f"add {j}, {j}, 1", f"jmp {ch}"],
        ce: [f"add {i}, {i}, 1", f"jmp {rh}"],
        done: [f"load {output}, {c}", f"add {output}, {output}, {i}", f"add {output}, {output}, {j}",
               f"add {output}, {output}, {k}", f"add {output}, {output}, {test}", f"ret {output}"],
    }
    order=labels[1:];rng.shuffle(order)
    return "func generated(v0, v1)\n"+"".join(label+":\n  "+"\n  ".join(blocks[label])+"\n" for label in [entry,*order])


def loop(body, setup="const v2, 0", bound="4", ending="ret v3"):
    return (f"func generated(v0, v1)\nentry:\n  {setup}\n  jmp head\nhead:\n  lt v4, v2, {bound}\n"
            f"  br v4, body, done\nbody:\n  "+"\n  ".join(body)+
            f"\n  add v2, v2, 1\n  jmp head\ndone:\n  {ending}\n")


def fixtures():
    rng=random.Random(928174)
    cases=[]
    for rows,cols,depth in ((1,1,1),(2,3,4),(4,2,3),(3,4,2),(4,4,4),(3,2,0)):
        for a,b,c in ((0,32,64),(0,0,0),(3070,3072,3080),(4094,32,700)):
            cases.append((matrix(rng,rows,cols,depth,a,b,c),True))
    for variant in ("volatile","unknown_address","divide","unknown_branch"):
        cases.append((matrix(rng,2,2,2,variant=variant),variant!="unknown_branch"))
    cases += [
        (loop(["add v3, v3, v0"]),True), # implicit-zero nonparameters
        (loop(["add v3, v3, v0"],setup="const v2, -2",bound="2"),True),
        (loop(["store 3071, v2","load v3, 4096"]),True),
        (loop(["vstore 7, v2","div v3, 1, 0"]),True),
        (loop(["load v3, v2"],ending="trap v0"),True),
        (loop(["mac v3, 7, 9, 11","addsh v3, v3, 1, 31","shl v3, v3, 33"]),True),
        (loop(["add v3, v3, 1"],bound="v0"),False),
        (loop(["add v3, v3, 1"],bound="100000"),False),
        (loop(["load v3, 0","store 1, v3"],bound="2000"),False),
        ("func infinite()\nentry:\n  jmp entry\nunused:\n  ret 0\n",False),
        (matrix(rng,0,2,2),False),
    ]
    return cases


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("kit",type=Path);args=parser.parse_args()
    sys.dont_write_bytecode=True;kit=args.kit.resolve()
    sys.path.insert(0,str(kit));sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    import kirlib as ref
    from src.expansion import cache_loads, expand
    from src.kirlib import parse_program
    from src.optimizer import optimize
    rng=random.Random(649173);outcomes=Counter();comparisons=accepted=unsupported=cached_pairs=0
    machines={p.stem:ref.load_machine(p) for p in sorted((kit/'machines').glob('*.cfg'))}
    default=ref.load_machine(kit/'machines/machine_default.cfg')
    machines.update({name:default|values for name,values in MACHINE_VARIANTS.items()})
    edges=(0,1,3071,3072,4095,4096,0xFFFFFFFF,0x80000000)
    inputs=[([edges[i%8],edges[(i+3)%8]],[(0,[rng.getrandbits(32) for _ in range(4096)])],{7:[0,1,0xFFFFFFFF,0x80000000]}) for i in range(16)]
    with tempfile.TemporaryDirectory(prefix='oxygen-expansion-') as folder:
        work=Path(folder);source=work/'source.kir';output=work/'out.kir'
        for name,mc in machines.items():(work/f'{name}.cfg').write_text(''.join(f'{k} = {v}\n' for k,v in mc.items()))
        for index,(text,expected) in enumerate(fixtures()):
            source.write_text(text);original=ref.compile_program(ref.load_program(source))
            expanded=expand(parse_program(text))
            if (expanded is not None)!=expected:raise RuntimeError(f'proof expectation {index}: {expected}')
            if expanded is None:continue
            accepted+=1
            output.write_text(expanded);direct=ref.compile_program(ref.load_program(output))
            references=[ref.execute(original,*data,100000) for data in inputs]
            if any(before.status=='TIMEOUT' for before in references):raise RuntimeError(f'nonterminating positive {index}')
            for name,mc in machines.items():
                try:
                    ref.check_machine_features(ref.load_program(source),mc)
                except ref.KirError:
                    unsupported+=1
                    continue
                cleaned=optimize(parse_program(expanded),expanded,mc)
                output.write_text(cleaned if cleaned is not None else expanded)
                parsed=ref.load_program(output);ref.check_machine_features(parsed,mc);unselected=ref.compile_program(parsed)
                variants=[('direct',direct),('unselected',unselected)]
                cached=cache_loads(parse_program(expanded),min(16,max(4,mc['registers'])))
                if cached is not None:
                    cached_pairs+=1
                    output.write_text(cached);variants.append(('cached',ref.compile_program(ref.load_program(output))))
                    cleaned=optimize(parse_program(cached),cached,mc)
                    output.write_text(cleaned if cleaned is not None else cached)
                    parsed=ref.load_program(output);ref.check_machine_features(parsed,mc)
                    variants.append(('cached-unselected',ref.compile_program(parsed)))
                subprocess.run([Path(__file__).resolve().parents[1]/'kopt',source,'--machine',work/f'{name}.cfg','-o',output],
                               capture_output=True,check=True,timeout=5)
                parsed=ref.load_program(output);ref.check_machine_features(parsed,mc);selected=ref.compile_program(parsed)
                for data,before in zip(inputs,references):
                    for kind,compiled in [*variants,('selected',selected)]:
                        after=ref.execute(compiled,*data,100000)
                        difference=ref.first_difference(before,after)
                        if difference:raise RuntimeError(f'{index}, {name}, {data[0]}, {kind}: {difference}\n{text}')
                        comparisons+=1
                    outcomes[before.status if before.status=='RET' else before.value]+=1
    if not cached_pairs:raise RuntimeError('missing cached-load coverage')
    print(f'{len(fixtures())} static-control fixtures, {accepted} expanded, {cached_pairs} cached pairs, {len(machines)} machines × 16 inputs: '
          f'{comparisons:,} direct/unselected/selected matches; {dict(outcomes)}; zero reference timeouts; '
          f'{unsupported} source/machine feature mismatches skipped')


if __name__=='__main__':main()
