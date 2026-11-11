"""Execution and timing copied from the permitted organizer COMP10 kit.

Upstream commit d23ac1d865df4cdacf7ad8e9fff3e1d560761c46, kirlib.py.
Used for exhaustive source-derived specialization and machine-cost comparison.
The parser and machine configuration reader remain in src.kirlib.
"""
from collections import OrderedDict, deque

from .kirlib import MASK, TERMINATORS

SIGN = 0x80000000
MEM_WORDS = 4096

MEM_OPS = ('load', 'store', 'vload', 'vstore')
LATKEY = {
    'const': 'lat_alu', 'mov': 'lat_alu', 'add': 'lat_alu', 'sub': 'lat_alu', 'and': 'lat_alu',
    'or': 'lat_alu', 'xor': 'lat_alu', 'shl': 'lat_alu', 'shr': 'lat_alu', 'lt': 'lat_alu',
    'eq': 'lat_alu', 'select': 'lat_alu', 'mul': 'lat_mul', 'div': 'lat_div', 'mod': 'lat_div',
    'load': 'lat_load', 'vload': 'lat_load', 'mac': 'lat_mac', 'addsh': 'lat_addsh',
}

(ADD, SUB, MUL, AND, OR, XOR, SHL, SHR, LT, EQ, MOV, SELECT, LOAD, STORE, DIV, MOD,
 MAC, ADDSH, VLOAD, VSTORE, TRAP, JMP, BR, RET) = range(24)
OPID = {'add': ADD, 'sub': SUB, 'mul': MUL, 'and': AND, 'or': OR, 'xor': XOR, 'shl': SHL,
        'shr': SHR, 'lt': LT, 'eq': EQ, 'const': MOV, 'mov': MOV, 'select': SELECT,
        'load': LOAD, 'store': STORE, 'div': DIV, 'mod': MOD, 'mac': MAC, 'addsh': ADDSH,
        'vload': VLOAD, 'vstore': VSTORE, 'trap': TRAP, 'jmp': JMP, 'br': BR, 'ret': RET}


class Compiled(object):
    pass


def compile_program(prog):
    regmap = {}

    def rid(idx):
        if idx not in regmap:
            regmap[idx] = len(regmap)
        return regmap[idx]

    for p in prog.params:
        rid(p)
    for ins in prog.instrs:
        for kind, val in ins.args:
            if kind == 'r':
                rid(val)
    nregs = len(regmap)
    consts = {}

    def slot(operand):
        kind, val = operand
        if kind == 'r':
            return regmap[val]
        if val not in consts:
            consts[val] = nregs + len(consts)
        return consts[val]

    cp = Compiled()
    code, srcs, dst, opnames = [], [], [], []
    for ins in prog.instrs:
        op, a = ins.op, ins.args
        d = x = y = z = t1 = t2 = 0
        src_slots = []
        dest = -1
        if op == 'const':
            d, x = slot(a[0]), slot(a[1]); dest = d
        elif op == 'mov':
            d, x = slot(a[0]), slot(a[1]); dest = d; src_slots = [x]
        elif op in ('add', 'sub', 'mul', 'and', 'or', 'xor', 'shl', 'shr', 'lt', 'eq', 'div', 'mod'):
            d, x, y = slot(a[0]), slot(a[1]), slot(a[2]); dest = d; src_slots = [x, y]
        elif op in ('select', 'mac'):
            d, x, y, z = slot(a[0]), slot(a[1]), slot(a[2]), slot(a[3]); dest = d; src_slots = [x, y, z]
        elif op == 'addsh':
            d, x, y, z = slot(a[0]), slot(a[1]), slot(a[2]), a[3][1]; dest = d; src_slots = [x, y]
        elif op in ('load', 'vload'):
            d, x = slot(a[0]), slot(a[1]); dest = d; src_slots = [x]
        elif op in ('store', 'vstore'):
            x, y = slot(a[0]), slot(a[1]); src_slots = [x, y]
        elif op in ('trap', 'ret'):
            x = slot(a[0]); src_slots = [x]
        elif op == 'jmp':
            t1 = prog.labels[a[0][1]]
        elif op == 'br':
            x = slot(a[0]); t1 = prog.labels[a[1][1]]; t2 = prog.labels[a[2][1]]; src_slots = [x]
        code.append((OPID[op], d, x, y, z, t1, t2))
        srcs.append(tuple(s for s in src_slots if s < nregs))
        dst.append(dest)
        opnames.append(op)
    cp.code = code
    cp.srcs = srcs
    cp.dst = dst
    cp.opnames = opnames
    cp.touch = []
    for i in range(len(code)):
        seen, order = set(), []
        for r in list(srcs[i]) + ([dst[i]] if dst[i] >= 0 else []):
            if r not in seen:
                seen.add(r); order.append(r)
        cp.touch.append(tuple(order))
    cp.isterm = [n in TERMINATORS for n in opnames]
    cp.ismem = [n in MEM_OPS for n in opnames]
    cp.nregs = nregs
    cp.nparams = len(prog.params)
    cp.R0 = [0] * nregs + [v for v, _ in sorted(consts.items(), key=lambda kv: kv[1])]
    cp.text = [ins.text for ins in prog.instrs]
    cp.block_of = prog.block_of
    cp.name = prog.name
    return cp


# --------------------------------------------------------------------------
# Execution (exact semantics)
# --------------------------------------------------------------------------
class Result(object):
    __slots__ = ('status', 'value', 'vlog', 'mem', 'steps', 'trace')

    def __init__(self, status, value, vlog, mem, steps, trace):
        self.status = status    # 'RET', 'TRAP' or 'TIMEOUT'
        self.value = value      # unsigned return value (RET) or trap kind string (TRAP)
        self.vlog = vlog        # list of ('L'|'S', port, value)
        self.mem = mem
        self.steps = steps
        self.trace = trace


def execute(cp, args, segments, vin, max_steps, want_trace=False):
    """args: list of ints; segments: list of (addr, [words]); vin: {port: [words]}"""
    R = cp.R0[:]
    for i, v in enumerate(args):
        R[i] = v & MASK
    mem = [0] * MEM_WORDS
    for addr, words in segments:
        mem[addr:addr + len(words)] = words
    queues = dict((p, deque(w)) for p, w in vin.items())
    vlog = []
    code = cp.code
    tr = [] if want_trace else None
    pc = 0
    steps = 0
    while True:
        if steps >= max_steps:
            return Result('TIMEOUT', None, vlog, mem, steps, tr)
        op, d, a, b, c, t1, t2 = code[pc]
        steps += 1
        if want_trace:
            tr.append(pc)
        if op == ADD:
            R[d] = (R[a] + R[b]) & MASK; pc += 1
        elif op == MOV:
            R[d] = R[a]; pc += 1
        elif op == LT:
            R[d] = 1 if (R[a] ^ SIGN) < (R[b] ^ SIGN) else 0; pc += 1
        elif op == BR:
            pc = t1 if R[a] != 0 else t2
        elif op == JMP:
            pc = t1
        elif op == SUB:
            R[d] = (R[a] - R[b]) & MASK; pc += 1
        elif op == MUL:
            R[d] = (R[a] * R[b]) & MASK; pc += 1
        elif op == AND:
            R[d] = R[a] & R[b]; pc += 1
        elif op == OR:
            R[d] = R[a] | R[b]; pc += 1
        elif op == XOR:
            R[d] = R[a] ^ R[b]; pc += 1
        elif op == SHL:
            R[d] = (R[a] << (R[b] & 31)) & MASK; pc += 1
        elif op == SHR:
            R[d] = R[a] >> (R[b] & 31); pc += 1
        elif op == EQ:
            R[d] = 1 if R[a] == R[b] else 0; pc += 1
        elif op == SELECT:
            R[d] = R[b] if R[a] != 0 else R[c]; pc += 1
        elif op == LOAD:
            addr = R[a]
            if addr >= MEM_WORDS:
                return Result('TRAP', 'bad_address', vlog, mem, steps, tr)
            R[d] = mem[addr]; pc += 1
        elif op == STORE:
            addr = R[a]
            if addr >= MEM_WORDS:
                return Result('TRAP', 'bad_address', vlog, mem, steps, tr)
            mem[addr] = R[b]; pc += 1
        elif op == MAC:
            R[d] = (R[a] * R[b] + R[c]) & MASK; pc += 1
        elif op == ADDSH:
            R[d] = (R[a] + (R[b] << c)) & MASK; pc += 1
        elif op == DIV or op == MOD:
            y = R[b]
            if y == 0:
                return Result('TRAP', 'div_by_zero', vlog, mem, steps, tr)
            x = R[a]
            sx = x - 0x100000000 if x & SIGN else x
            sy = y - 0x100000000 if y & SIGN else y
            if op == DIV:
                q = abs(sx) // abs(sy)
                if (sx < 0) != (sy < 0):
                    q = -q
                R[d] = q & MASK
            else:
                r = abs(sx) % abs(sy)
                if sx < 0:
                    r = -r
                R[d] = r & MASK
            pc += 1
        elif op == VLOAD:
            port = R[a]
            q = queues.get(port)
            val = q.popleft() if q else 0
            vlog.append(('L', port, val))
            R[d] = val; pc += 1
        elif op == VSTORE:
            vlog.append(('S', R[a], R[b])); pc += 1
        elif op == TRAP:
            return Result('TRAP', 'explicit(%d)' % R[a], vlog, mem, steps, tr)
        else:  # RET
            return Result('RET', R[a], vlog, mem, steps, tr)


# --------------------------------------------------------------------------
# Timing model (see KIR_SPEC.md, section "Cycle accounting")
# --------------------------------------------------------------------------
def time_trace(cp, trace, mc, issue_out=None):
    """Return the exact cycle count for a finished run (trace = executed instruction indices)."""
    W, MP, K = mc['issue_width'], mc['mem_ports'], mc['registers']
    SP, TB = mc['reg_spill_penalty'], mc['taken_branch_penalty']
    IC, ICP = mc['icache_size'], mc['icache_penalty']
    lat = [mc[LATKEY[n]] if n in LATKEY else 1 for n in cp.opnames]
    srcs, dst, touch, isterm, ismem = cp.srcs, cp.dst, cp.touch, cp.isterm, cp.ismem
    ready = [0] * cp.nregs
    track = cp.nregs > K
    resident = OrderedDict()
    spilled = set()
    if track:
        for r in range(cp.nparams):
            if len(resident) >= K:
                spilled.add(resident.popitem(last=False)[0])
            resident[r] = True
    last = 0      # issue cycle of the previous instruction
    used = 0      # instructions already issued in cycle `last`
    memused = 0   # memory instructions already issued in cycle `last`
    fence = 0     # earliest cycle the next instruction may issue (after a taken transfer)
    n = len(trace)
    for idx in range(n):
        pc = trace[idx]
        F = ICP if pc >= IC else 0
        if track:
            for r in touch[pc]:
                if r in resident:
                    resident.move_to_end(r)
                else:
                    if r in spilled:
                        F += SP
                        spilled.discard(r)
                    if len(resident) >= K:
                        spilled.add(resident.popitem(last=False)[0])
                    resident[r] = True
        t = last + F
        if fence > t:
            t = fence
        for r in srcs[pc]:
            if ready[r] > t:
                t = ready[r]
        d = dst[pc]
        if d >= 0 and ready[d] > t:
            t = ready[d]
        m = ismem[pc]
        if t == last and (used >= W or (m and memused >= MP)):
            t += 1
        if t > last:
            used = 0
            memused = 0
        used += 1
        if m:
            memused += 1
        last = t
        if d >= 0:
            ready[d] = t + lat[pc]
        if isterm[pc] and idx + 1 < n and trace[idx + 1] != pc + 1:
            fence = t + 1 + TB
        if issue_out is not None:
            issue_out.append(t)
    return last + 1
