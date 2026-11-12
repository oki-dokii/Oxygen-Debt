"""Counted groups with a complete scalar tail and signed nonwrap proofs."""

from collections import Counter

from .control import Fresh, after, counting, emit, graph, parents, pre_facts
from .kirlib import SIGS
from .ranges import MAX, entry_intervals, interval


def group(program, factor, placement='tail', require_minimum=True, _ranges=None):
    """Skip only tests proved true for every body in a group.

    For invariant s>0, i<n-(U-1)s proves all U original tests true.
    Production also proves a whole first group; the generic entry-guarded
    form is available only to direct tests. Static ranges include the final
    increment, so the next group cannot enter
    with a wrapped negative index. Scalar entry/exit tests remain unchanged.
    """
    if factor not in (2,4,8) or placement not in ('tail','group','original') or len(program.instrs)>500 or len(program.block_labels)>128:
        return None
    blocks=graph(program);incoming=parents(blocks);ranges=_ranges;fresh=Fresh(program)
    try:
        for head in list(blocks):
            shape=counting(blocks,head,incoming)
            if shape is None:continue
            cond,counter,bound,label,done=shape;body=blocks[label]
            if (incoming[label]!=[head] or not 3<=len(body)<=32
                    or body[-1].op!='jmp' or body[-1].args!=[('l',head)]):continue
            if require_minimum and not any(ins.op in {'load','store','vload','vstore'} for ins in body):continue
            if len(incoming[head])!=2 or label not in incoming[head]:continue
            pre=next(owner for owner in incoming[head] if owner!=label)
            if (pre in (head,label,done) or blocks[pre][-1].op!='jmp'
                    or blocks[pre][-1].args!=[('l',head)]):continue
            update=body[-2];tail=1
            if update.op=='mov' and update.args[0]==counter and len(body)>=4:
                update=body[-3];tail=2
                if update.args[0]!=body[-2].args[1]:continue
            if update.op!='add' or counter not in update.args[1:]:continue
            if tail==1 and update.args[0]!=counter:continue
            step=update.args[2] if update.args[1]==counter else update.args[1]
            written=Counter(ins.args[0][1] for ins in body if SIGS[ins.op].startswith('d'))
            if (step==cond or written[counter[1]]!=1
                    or bound[0]=='r' and bound[1] in written
                    or step[0]=='r' and step[1] in written):continue
            # A two-instruction update must read its own just-written value.
            # Other writes to that temporary could change the claimed stride.
            if tail==2 and written[update.args[0][1]]!=1:continue
            if ranges is None:ranges=entry_intervals(blocks)
            facts=pre_facts(blocks,pre,ranges)
            initial=interval(facts,counter);limit=interval(facts,bound);stride=interval(facts,step)
            if min(initial[0],limit[0])<0 or not 1<=stride[0]<=stride[1]<=4096:continue
            if max(initial[1],limit[1]-1+stride[1])>MAX:continue
            guaranteed=initial[1]+(factor-1)*stride[1]<limit[0]
            if require_minimum and not guaranteed:continue
            distance,threshold,test=fresh.reg(),fresh.reg(),fresh.reg()
            gate='kopt_group_gate';chunk='kopt_group_body';setup='kopt_group_init';scalar='kopt_group_tail'
            while gate in blocks:gate+='x'
            while chunk in blocks or chunk==gate:chunk+='x'
            while setup in blocks or setup in (gate,chunk):setup+='x'
            while scalar in blocks or scalar in (gate,chunk,setup):scalar+='x'
            # Keep the original zero-trip entry path. Setup is reached only
            # after the original comparison proved at least one iteration.
            blocks[head][-1]=fresh.ins('br',cond,('l',setup),('l',done))
            blocks[label][-1]=fresh.ins('jmp',('l',scalar))
            blocks[setup]=[
                fresh.ins('mul',distance,step,('i',factor-1)),
                fresh.ins('sub',threshold,bound,distance),fresh.ins('lt',test,counter,threshold),
                fresh.ins('br',test,('l',chunk),('l',label))]
            blocks[gate]=[fresh.ins('lt',test,counter,threshold),
                          fresh.ins('br',test,('l',chunk),('l',head))]
            copies=[]
            for _ in range(factor):
                # The original header writes one before every executed body.
                copies.append(fresh.ins('const',cond,('i',1)))
                copies.extend(fresh.ins(ins.op,*ins.args) for ins in body[:-1])
            blocks[chunk]=copies+[fresh.ins('jmp',('l',gate))]
            blocks[scalar]=[fresh.ins('lt',cond,counter,bound),
                            fresh.ins('br',cond,('l',label),('l',done))]
            if guaranteed:
                # The first whole group is statically guaranteed, so neither
                # a speculative setup on a short path nor an entry test is needed.
                blocks[pre][-1:]=[fresh.ins('mul',distance,step,('i',factor-1)),
                    fresh.ins('sub',threshold,bound,distance),fresh.ins('jmp',('l',chunk))]
                blocks[head][-1]=fresh.ins('br',cond,('l',label),('l',done))
                blocks[label][-1]=fresh.ins('jmp',('l',head))
                blocks[gate][-1]=fresh.ins('br',test,('l',chunk),('l',head))
                del blocks[setup];del blocks[scalar]
                if placement=='tail':blocks=after(blocks,pre,[head,label,chunk,gate])
                elif placement=='group':blocks=after(blocks,pre,[chunk,gate])
                return emit(program,blocks)
            if placement=='tail':blocks=after(blocks,head,[setup,scalar,label])
            elif placement=='group':blocks=after(blocks,head,[setup,gate,chunk,scalar,label])
            return emit(program,blocks)
    except OverflowError:
        pass
    return None


def candidates(program):
    """Share range analysis across at most nine production candidates."""
    if len(program.instrs)>500 or len(program.block_labels)>128:return []
    blocks=graph(program);incoming=parents(blocks)
    shapes=[counting(blocks,head,incoming) for head in blocks]
    if not any(shape is not None and blocks[shape[3]][-1].op=='jmp'
               and blocks[shape[3]][-1].args==[('l',head)]
               and any(ins.op in {'load','store','vload','vstore'} for ins in blocks[shape[3]])
               for head,shape in zip(blocks,shapes)):return []
    ranges=entry_intervals(blocks)
    result=[]
    for factor in (2,4,8):
        for placement in ('tail','group','original'):
            text=group(program,factor,placement,_ranges=ranges)
            if text is not None:result.append(text)
    return result
