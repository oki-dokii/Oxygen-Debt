"""Proved affine diamonds, guarded counting loops and pointer induction."""

from collections import Counter

from .kirlib import Instr, MASK, SIGS
from .modulo import bounds
from .ranges import MAX, MIN, entry_intervals, interval, record
from .registers import register_names, register_reads
from .rolling import affine


def graph(program):
    starts=[program.labels[label] for label in program.block_labels]
    return {label:program.instrs[a:b] for label,a,b in
            zip(program.block_labels,starts,[*starts[1:],len(program.instrs)])}


def emit(program,blocks):
    params=', '.join(f'v{r}' for r in program.params)
    lines=[f'func {program.name}({params})']
    for label,block in blocks.items():
        lines.append(label+':')
        for ins in block:
            lines.append('  '+ins.op+' '+', '.join(f'v{value}' if tag=='r' else str(value) for tag,value in ins.args))
    return '\n'.join(lines)+'\n'


def parents(blocks):
    result={label:[] for label in blocks}
    for label,block in blocks.items():
        for target in dict.fromkeys(value for tag,value in block[-1].args if tag=='l'):
            result[target].append(label)
    return result


def after(blocks,anchor,moved):
    result={}
    for label,body in blocks.items():
        if label in moved:continue
        result[label]=body
        if label==anchor:
            for name in moved:result[name]=blocks[name]
    return result


class Fresh:
    def __init__(self,program):
        self.register=max(register_names(program.instrs)|set(program.params),default=-1)+1
        self.line=max(ins.line for ins in program.instrs)+1

    def reg(self):
        if self.register>999999:raise OverflowError()
        result=('r',self.register);self.register+=1;return result

    def ins(self,op,*args):
        result=Instr(op,list(args),self.line,'');self.line+=1;return result


def linear_arm(block):
    values={}
    for ins in block[:-1]:
        def read(arg):
            tag,value=arg
            return values.get(value,{value:1}) if tag=='r' else {None:value}
        args=[read(arg) for arg in ins.args[1:]]
        if ins.op in {'const','mov'}:value=args[0].copy()
        elif ins.op in {'add','sub'}:
            value=args[0].copy();sign=-1 if ins.op=='sub' else 1
            for key,coefficient in args[1].items():value[key]=(value.get(key,0)+sign*coefficient)&MASK
        else:return None
        values[ins.args[0][1]]={key:c for key,c in value.items() if c}
    return values


def arm_inputs(block):
    defined=set();inputs=set()
    for ins in block[:-1]:
        inputs.update(set(register_reads(ins))-defined)
        defined.add(ins.args[0][1])
    return inputs


def diamonds(program):
    blocks=graph(program);incoming=parents(blocks);fresh=Fresh(program);changed=False
    for owner,block in blocks.items():
        branch=block[-1]
        if branch.op!='br':continue
        cond,yes,no=branch.args;left_label,right_label=yes[1],no[1]
        if left_label==right_label or next(iter(blocks)) in (left_label,right_label):continue
        if incoming[left_label]!=[owner] or incoming[right_label]!=[owner]:continue
        left,right=blocks[left_label],blocks[right_label]
        if not (2<=len(left)<=5 and 2<=len(right)<=5 and left[-1].op==right[-1].op=='jmp'
                and left[-1].args==right[-1].args):continue
        a,b=linear_arm(left),linear_arm(right)
        if a is None or b is None:continue
        outside={r for label,items in blocks.items() if label not in (left_label,right_label)
                 for ins in items for r in register_reads(ins)}
        outside.update(arm_inputs(left)|arm_inputs(right))
        escaping_a,escaping_b=a.keys()&outside,b.keys()&outside
        if escaping_a!=escaping_b or len(escaping_a)!=1:continue
        dest=next(iter(escaping_a));yes_value,no_value=a[dest],b[dest]
        yes_terms={k:c for k,c in yes_value.items() if k is not None}
        no_terms={k:c for k,c in no_value.items() if k is not None}
        if yes_terms!=no_terms or len(yes_terms)!=1:continue
        base,coefficient=next(iter(yes_terms.items()))
        if coefficient!=1:continue
        selected=fresh.reg()
        block[-1:]=[fresh.ins('select',selected,cond,('i',yes_value.get(None,0)),('i',no_value.get(None,0))),
                    fresh.ins('add',('r',dest),('r',base),selected),fresh.ins('jmp',*left[-1].args)]
        changed=True
    return emit(program,blocks) if changed else None


def pre_facts(blocks,label,incoming):
    facts=incoming.get(label,{}).copy()
    for ins in blocks[label][:-1]:
        if SIGS[ins.op].startswith('d'):
            record(facts,ins.args[0],bounds(ins.op,ins.args[1:],facts))
    return facts


def counting(blocks,head,incoming):
    header=blocks[head]
    if head==next(iter(blocks)) or len(header)!=2 or header[0].op!='lt' or header[1].op!='br':return None
    cond,counter,bound=header[0].args
    if counter[0]!='r' or counter==bound or cond in (counter,bound) or header[1].args[0]!=cond:return None
    body,done=(arg[1] for arg in header[1].args[1:])
    if len({head,body,done})!=3 or next(iter(blocks)) in (body,done):return None
    return cond,counter,bound,body,done


def guards(program):
    blocks=graph(program);incoming=parents(blocks);ranges=entry_intervals(blocks);fresh=Fresh(program)
    for head in list(blocks):
        shape=counting(blocks,head,incoming)
        if shape is None:continue
        cond,counter,bound,guard,done=shape;check=blocks[guard]
        if incoming[guard]!=[head] or len(check) not in (2,3) or check[0].op!='lt' or check[-1].op!='br':continue
        flag,index,limit=check[0].args
        if index!=counter or limit[0]!='i' or not 0<=limit[1]<=4096 or flag in (counter,bound):continue
        true,false=(arg[1] for arg in check[-1].args[1:])
        definitions={flag[1]}
        if len(check)==3:
            negation=check[1]
            if negation.op!='eq' or negation.args[1:] not in ([flag,('i',0)],[('i',0),flag]):continue
            definitions.add(negation.args[0][1]);flag=negation.args[0];true,false=false,true
        if check[-1].args[0]!=flag:continue
        work,trap=true,false
        if (len({head,guard,work,trap,done})!=5 or next(iter(blocks)) in (work,trap)
                or blocks[trap][-1].op!='trap'):continue
        body=blocks[work]
        if len(body)>128 or incoming[work]!=[guard] or body[-1].op!='jmp' or body[-1].args!=[('l',head)]:continue
        if len(incoming[head])!=2 or work not in incoming[head]:continue
        pre=next(label for label in incoming[head] if label!=work)
        if pre in (head,guard,work,trap,done) or blocks[pre][-1].op!='jmp' or blocks[pre][-1].args!=[('l',head)]:continue
        outside={r for label,items in blocks.items() if label!=guard for ins in items for r in register_reads(ins)}
        if definitions&outside:continue
        written={ins.args[0][1] for ins in body if SIGS[ins.op].startswith('d')}
        if bound[0]=='r' and bound[1] in written:continue
        facts=pre_facts(blocks,pre,ranges)
        if interval(facts,counter)!=(0,0):continue
        values={counter[1]:(1,0)}
        for ins in body[:-1]:
            if SIGS[ins.op].startswith('d'):
                sources=[values.get(v) if tag=='r' else (0,v) for tag,v in ins.args[1:]]
                values[ins.args[0][1]]=affine(ins.op,sources)
        if values.get(counter[1])!=(1,1):continue
        choose,clamped,late=fresh.reg(),fresh.reg(),fresh.reg()
        blocks[pre][-1:-1]=[fresh.ins('lt',choose,bound,limit),fresh.ins('select',clamped,choose,bound,limit)]
        blocks[head][0]=fresh.ins('lt',cond,counter,clamped)
        post='kopt_guard_exit'
        while post in blocks:post+='x'
        blocks[head][-1]=fresh.ins('br',cond,('l',work),('l',post))
        blocks[post]=[fresh.ins('lt',late,limit,bound),fresh.ins('mov',cond,late),
                      fresh.ins('br',late,('l',trap),('l',done))]
        del blocks[guard]
        return emit(program,after(blocks,head,[work]))
    return None


def pointers(program):
    blocks=graph(program);incoming=parents(blocks);ranges=entry_intervals(blocks);fresh=Fresh(program)
    for head in blocks:
        shape=counting(blocks,head,incoming)
        if shape is None:continue
        cond,counter,bound,label,done=shape;body=blocks[label]
        if incoming[label]!=[head] or len(body)>128 or len(body)<3 or body[-1].op!='jmp' or body[-1].args!=[('l',head)]:continue
        if len(incoming[head])!=2 or label not in incoming[head]:continue
        pre=next(p for p in incoming[head] if p!=label)
        if pre in (head,label,done) or blocks[pre][-1].op!='jmp' or blocks[pre][-1].args!=[('l',head)]:continue
        update=body[-2];tail=1
        if update.op=='mov' and update.args[0]==counter and len(body)>=4:
            update=body[-3];tail=2
            if update.args[0]!=body[-2].args[1]:continue
        if update.op!='add' or counter not in update.args[1:]:continue
        if tail==1 and update.args[0]!=counter:continue
        step=update.args[2] if update.args[1]==counter else update.args[1]
        if step==cond:continue
        counts=Counter(ins.args[0][1] for ins in body if SIGS[ins.op].startswith('d'))
        if counts[counter[1]]!=1 or (bound[0]=='r' and bound[1] in counts) or (step[0]=='r' and step[1] in counts):continue
        if update.args[0]!=counter and counts[update.args[0][1]]!=1:continue
        outside={r for owner,items in blocks.items() if owner not in (head,label) for ins in items for r in register_reads(ins)}
        if counter[1] in outside or (update.args[0]!=counter and update.args[0][1] in outside):continue
        facts=pre_facts(blocks,pre,ranges)
        start=interval(facts,counter);bound_range=interval(facts,bound);stride=interval(facts,step)
        if min(start[0],bound_range[0])<0 or not 1<=stride[0]<=stride[1]<=4096:continue
        maximum=max(start[1],bound_range[1]-1+stride[1])
        if maximum>MAX:continue
        for pos,address in enumerate(body[:-tail-1]):
            if address.op!='add' or counter not in address.args[1:]:continue
            offset=address.args[2] if address.args[1]==counter else address.args[1]
            if offset[0]!='i':continue
            offset_value=offset[1] if offset[1]<=MAX else offset[1]-(MASK+1)
            dest=address.args[0]
            if dest in (counter,bound,step,cond,update.args[0]) or counts[dest[1]]!=1 or dest[1] in outside:continue
            if not MIN<=min(start[0],bound_range[0])+offset_value<=maximum+offset_value<=MAX:continue
            valid=True
            for index,ins in enumerate(body[:-1]):
                if counter[1] in register_reads(ins) and ins is not address and ins is not update:valid=False
                if dest[1] in register_reads(ins) and not pos<index<len(body)-tail-1:valid=False
                if update.args[0]!=counter and update.args[0][1] in register_reads(ins) and ins is not body[-2]:valid=False
            if not valid:continue
            end=fresh.reg()
            blocks[pre][-1:-1]=[fresh.ins('add',counter,counter,offset),fresh.ins('add',end,bound,offset)]
            blocks[head][0]=fresh.ins('lt',cond,counter,end)
            blocks[label]=[fresh.ins(ins.op,*[(tag,counter[1]) if tag=='r' and value==dest[1] else (tag,value)
                                           for tag,value in ins.args]) for ins in body if ins is not address]
            return emit(program,blocks)
    return None


def unroll(program):
    """Four checked copies: each transition still performs the original test."""
    blocks=graph(program);incoming=parents(blocks);fresh=Fresh(program)
    for head in list(blocks):
        shape=counting(blocks,head,incoming)
        if shape is None:continue
        cond,counter,bound,label,done=shape;body=blocks[label]
        if incoming[label]!=[head] or not 2<=len(body)<=32 or body[-1].op!='jmp' or body[-1].args!=[('l',head)]:continue
        labels=[label]
        for index in range(3):
            name=f'kopt_checked_{index}'
            while name in blocks or name in labels:name+='x'
            labels.append(name)
        for index,name in enumerate(labels):
            blocks[name]=[fresh.ins(ins.op,*ins.args) for ins in body[:-1]]+[
                fresh.ins('lt',cond,counter,bound),fresh.ins('br',cond,('l',labels[(index+1)%4]),('l',done))]
        return emit(program,after(blocks,head,labels))
    return None


def rewrite(program,mode):
    if len(program.instrs)>500 or len(program.block_labels)>128:return None
    try:return {'diamonds':diamonds,'guards':guards,'pointers':pointers,'unroll':unroll}[mode](program)
    except OverflowError:return None
