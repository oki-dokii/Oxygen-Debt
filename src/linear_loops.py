"""Collapse bounded additive loops, including inner loops of a nest."""
from .kirlib import MASK, Instr, SIGS
from .arithmetic import simplify
from .ranges import entry_intervals, interval, update
from .registers import register_names, register_reads


def add(left,right,scale=1):
    if left is None or right is None:return None
    result=left.copy()
    for key,value in right.items():result[key]=(result.get(key,0)+scale*value)&MASK
    return {key:value for key,value in result.items() if value}


def scale(value,amount):
    return None if value is None else {key:coefficient*amount&MASK for key,coefficient in value.items() if coefficient*amount&MASK}


def scalar(value):
    return value.get(None,0) if value is not None and not value.keys()-{None} else None


def collapse(blocks,pure):
    if sum(map(len,blocks.values()))>2000:return None
    predecessors={label:[] for label in blocks}
    for label,block in blocks.items():
        for target in dict.fromkeys(v for k,v in block[-1].args if k=='l'):predecessors[target].append(label)
    incoming=entry_intervals(blocks)
    for head,header in blocks.items():
        if head==next(iter(blocks)) or len(header)!=2 or header[0].op!='lt' or header[1].op!='br':continue
        condition,index,bound=header[0].args
        if index[0]!='r' or condition==index or header[1].args[0]!=condition:continue
        body_label,exit_label=(arg[1] for arg in header[1].args[1:])
        if body_label in (head,exit_label,next(iter(blocks))) or predecessors[body_label]!=[head]:continue
        body=blocks[body_label]
        if body[-1].op!='jmp' or body[-1].args!=[('l',head)] or len(predecessors[head])!=2:continue
        if any(ins.op not in pure for ins in body[:-1]):continue
        preheader=next(label for label in predecessors[head] if label!=body_label)
        if blocks[preheader][-1].op!='jmp':continue
        written={ins.args[0][1] for ins in [*header,*body] if SIGS[ins.op].startswith('d')}
        if bound[0]=='r' and bound[1] in written:continue
        facts=incoming.get(preheader,{}).copy()
        for ins in blocks[preheader][:-1]:update(facts,ins.op,ins.args)
        low,high=interval(facts,bound)
        if not 0<=low<=high<=255 or interval(facts,index)!=(0,0):continue
        observed={r for label,block in blocks.items() if label not in (head,body_label) for ins in block for r in register_reads(ins)}&written
        candidates=observed-{index[1],condition[1]}
        if len(candidates)!=1:continue
        accumulator=next(iter(candidates));values={}
        def read(arg):
            if arg[0]!='r':return {None:arg[1]} if arg[1] else {}
            r=arg[1]
            if r in values:return values[r]
            if r in written:return {r:1} if r in (accumulator,index[1]) else None
            lo,hi=interval(facts,arg)
            return ({None:lo&MASK} if lo&MASK else {}) if lo==hi else {r:1}
        values[condition[1]]={None:1}
        for ins in body[:-1]:
            args=[read(arg) for arg in ins.args[1:]];op=ins.op;result=None
            constants=[scalar(arg) for arg in args]
            folded=simplify(op,[('i',n) for n in constants]) if all(n is not None for n in constants) else None
            if folded is not None:result={None:folded[1]} if folded[1] else {}
            elif op in ('mov','const'):result=args[0]
            elif op in ('add','sub'):result=add(*args,-1 if op=='sub' else 1)
            elif op=='mul':
                for i in (0,1):
                    n=scalar(args[i])
                    if n is not None:result=scale(args[1-i],n);break
            elif op=='shl' and scalar(args[1]) is not None:result=scale(args[0],1<<(scalar(args[1])&31))
            elif op=='addsh' and scalar(args[2]) is not None:result=add(args[0],scale(args[1],1<<scalar(args[2])))
            elif op=='mac':
                for i in (0,1):
                    n=scalar(args[i])
                    if n is not None:result=add(scale(args[1-i],n),args[2]);break
            values[ins.args[0][1]]=result
        result=values.get(accumulator)
        if (values.get(index[1])!={index[1]:1,None:1} or result is None or result.get(accumulator)!=1
                or any(r in written and r not in (index[1],accumulator) for r in result if r is not None)):continue
        register=max(register_names(ins for block in blocks.values() for ins in block),default=-1)+1
        line=max(ins.line for block in blocks.values() for ins in block)+1
        emitted=[]
        def emit(op,*sources):
            nonlocal register,line
            dest=('r',register);register+=1
            emitted.append(Instr(op,[dest,*sources],line,''));line+=1
            return dest
        if register+4*len(result)+16>=1000000:continue
        low_acc,high_acc=interval(facts,('r',accumulator))
        total=('i',low_acc&MASK) if low_acc==high_acc else ('r',accumulator)
        for r,coefficient in sorted(result.items(),key=lambda item:-1 if item[0] is None else item[0]):
            if r==accumulator:continue
            if r==index[1]:
                term=emit('mul',bound,emit('sub',bound,('i',1)))
                term=emit('shr',term,('i',1))
            elif r is None:term=bound
            else:term=emit('mul',bound,('r',r))
            if coefficient!=1:term=emit('mul',term,('i',coefficient))
            total=term if total==('i',0) else emit('add',total,term)
        outputs={accumulator:total,index[1]:bound,condition[1]:('i',0)}
        # Snapshot an invariant bound if it aliases another output destination.
        if bound[0]=='r' and bound[1] in observed:outputs[index[1]]=emit('mov',bound)
        for r in sorted(observed):
            value=outputs[r];emitted.append(Instr('mov' if value[0]=='r' else 'const',[('r',r),value],line,''));line+=1
        jump=blocks[preheader][-1];emitted.append(Instr('jmp',[('l',exit_label)],jump.line,jump.text))
        blocks[preheader][-1:]=emitted
        return preheader
    return None
