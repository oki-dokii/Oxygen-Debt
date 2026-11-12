"""Mutate all public sources and validate on new machines and wrong profiles."""
import argparse
from collections import Counter
import os
from pathlib import Path
import random
import subprocess
import sys
import tempfile


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('kit',type=Path);args=parser.parse_args()
    kit=args.kit.resolve();sys.dont_write_bytecode=True
    sys.path.insert(0,str(kit));sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    import kirlib as ref
    from src.kirlib import Instr, parse_program
    from src.optimizer import format_instruction
    rng=random.Random(427918)
    default=ref.load_machine(kit/'machines/machine_default.cfg')
    machines=[default|dict(registers=4,reg_spill_penalty=9,issue_width=1,lat_mul=1,lat_load=7,icache_size=32,icache_penalty=2,fused_mac=0,fused_addsh=0),
              default|dict(registers=7,reg_spill_penalty=3,issue_width=3,mem_ports=2,lat_alu=2,lat_mul=5,taken_branch_penalty=7),
              default|dict(registers=24,reg_spill_penalty=0,issue_width=6,mem_ports=3,lat_alu=3,lat_mul=1,lat_load=2,taken_branch_penalty=1)]
    matches=skipped=pairs=constant_changes=0;outcomes=Counter()
    with tempfile.TemporaryDirectory(prefix='oxygen-metamorphic-') as folder:
        work=Path(folder);input_path=work/'input.kir';output=work/'output.kir';profile=work/'wrong.prof'
        for i,mc in enumerate(machines):(work/f'machine{i}.cfg').write_text(''.join(f'{k} = {v}\n' for k,v in mc.items()))
        for number,path in enumerate(sorted((kit/'bench').glob('*.kir'))):
            for mutation in (False,True):
                program=parse_program(path.read_text());registers=sorted({value for ins in program.instrs for kind,value in ins.args if kind=='r'}|set(program.params))
                mapping=dict(zip(registers,rng.sample(range(10,990000),len(registers))))
                labels={label:f'block_{i}_{rng.randrange(100000)}' for i,label in enumerate(program.block_labels)}
                constants=[(i,j) for i,ins in enumerate(program.instrs) for j,(kind,_) in enumerate(ins.args) if kind=='i']
                changed=rng.choice(constants) if mutation and constants else None
                starts=[program.labels[k] for k in program.block_labels]
                blocks={label:program.instrs[a:b] for label,a,b in zip(program.block_labels,starts,[*starts[1:],len(program.instrs)])}
                order=program.block_labels[1:];rng.shuffle(order);order=[program.block_labels[0],*order]
                lines=['func metamorphic('+', '.join(f'v{mapping[r]}' for r in program.params)+')']
                index_of={id(ins):i for i,ins in enumerate(program.instrs)}
                for label in order:
                    lines.append(labels[label]+':')
                    for ins in blocks[label]:
                        operands=[]
                        for j,(kind,value) in enumerate(ins.args):
                            if kind=='r':value=mapping[value]
                            elif kind=='l':value=labels[value]
                            elif changed==(index_of[id(ins)],j):
                                value=rng.choice([word for word in (0,1,3,7,15,31,32,63,0xFFFFFFFF,0x80000000) if word!=value])
                                constant_changes+=1
                            operands.append((kind,value))
                        lines.append('  '+format_instruction(Instr(ins.op,operands,ins.line,'')))
                input_path.write_text('\n'.join(lines)+'\n');original_program=ref.load_program(input_path)
                mc_index=(number*2+mutation)%len(machines);mc=machines[mc_index]
                ref.check_machine_features(original_program,mc)
                # Invert likely branch weights and include a nonexistent edge.
                hints=['edge nonexistent other 99999999999']
                for ins in original_program.instrs:
                    if ins.op=='br':
                        origin=original_program.block_of[original_program.instrs.index(ins)]
                        hints += [f'edge {origin} {ins.args[1][1]} 1',f'edge {origin} {ins.args[2][1]} 999999']
                profile.write_text('\n'.join(hints)+'\n')
                outputs=[]
                for seed in ('1','87654321'):
                    process=subprocess.run([Path(__file__).resolve().parents[1]/'kopt',input_path,'--machine',work/f'machine{mc_index}.cfg','--profile',profile,'-o',output],
                                   env=os.environ|{'PYTHONHASHSEED':seed},capture_output=True,timeout=5)
                    if process.returncode:
                        raise RuntimeError(f'{path.stem}, mutation {mutation}, machine {mc_index}: {process.stderr.decode()}\n{input_path.read_text()}')
                    outputs.append(output.read_bytes())
                if outputs[0]!=outputs[1]:raise RuntimeError(f'non-determinism: {path.stem}, mutation {mutation}')
                transformed=ref.load_program(output);ref.check_machine_features(transformed,mc)
                original,optimized=map(ref.compile_program,(original_program,transformed))
                inputs=list(ref.generate_inputs(len(program.params),64,892471+number))
                sample=ref.load_input(path.with_suffix('.in'),len(program.params))
                inputs=[sample,*inputs[:4],*inputs[-4:]]
                for data in inputs:
                    before=ref.execute(original,data.args,data.segments,data.vin,20000)
                    if before.status=='TIMEOUT':skipped+=1;continue
                    after=ref.execute(optimized,data.args,data.segments,data.vin,20*before.steps+1000)
                    difference=ref.first_difference(before,after)
                    if difference:raise RuntimeError(f'{path.stem}, mutation {mutation}, machine {mc_index}: {difference}\n{input_path.read_text()}\n{ref.format_input(data)}')
                    matches+=1;outcomes[before.status]+=1
                pairs+=1
    print(f'{pairs} renamed/shuffled/constant-varied public-source cases across three new machines with wrong profiles: '
          f'{matches:,} matches; {skipped} references exceeded the 20,000-step limit and were skipped; {constant_changes} literal mutations; '
          f'deterministic across hash seeds; {dict(outcomes)}')

if __name__=='__main__':main()
