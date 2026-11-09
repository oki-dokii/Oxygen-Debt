"""KIR parser and machine loader adapted from the official COMP10 starter kit.

Source: rudra-shroff06/LLH-26, commit d23ac1d865df4cdacf7ad8e9fff3e1d560761c46.
The interpreter and timing model stay in the separate validation kit.
"""
import re

MASK = 0xFFFFFFFF
MAX_INSTRS = 500000
MAX_PARAMS = 8


class KirError(Exception):
    def __init__(self, msg, line=None):
        Exception.__init__(self, msg)
        self.msg = msg
        self.line = line

    def __str__(self):
        return ("line %d: %s" % (self.line, self.msg)) if self.line else self.msg


# Instruction table.  Signature letters:
#   d = destination register     s = source (register or integer literal)
#   i = integer literal          k = shift literal 0..31
#   L = label
# --------------------------------------------------------------------------
SIGS = {
    'const': 'di', 'mov': 'ds',
    'add': 'dss', 'sub': 'dss', 'mul': 'dss', 'and': 'dss', 'or': 'dss', 'xor': 'dss',
    'shl': 'dss', 'shr': 'dss', 'lt': 'dss', 'eq': 'dss', 'div': 'dss', 'mod': 'dss',
    'select': 'dsss', 'mac': 'dsss', 'addsh': 'dssk',
    'load': 'ds', 'store': 'ss', 'vload': 'ds', 'vstore': 'ss',
    'trap': 's', 'jmp': 'L', 'br': 'sLL', 'ret': 's',
}
TERMINATORS = ('jmp', 'br', 'ret', 'trap')


REG_RE = re.compile(r'^v(0|[1-9][0-9]{0,5})$')
NAME_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')
LIT_RE = re.compile(r'^-?(0x[0-9a-fA-F]+|[0-9]+)$')
FUNC_RE = re.compile(r'^func\s+([A-Za-z_][A-Za-z0-9_]*)\s*\((.*)\)$')
LABEL_RE = re.compile(r'^([A-Za-z_][A-Za-z0-9_]*):$')


def parse_literal_raw(tok, line=None):
    if not LIT_RE.match(tok):
        raise KirError("bad integer literal '%s'" % tok, line)
    neg = tok.startswith('-')
    body = tok[1:] if neg else tok
    n = int(body, 16) if body.startswith('0x') else int(body, 10)
    if neg:
        n = -n
    if n < -(1 << 31) or n > MASK:
        raise KirError("literal '%s' does not fit in 32 bits (allowed: -2147483648 .. 4294967295)" % tok, line)
    return n


# --------------------------------------------------------------------------
# Program parsing and validation
# --------------------------------------------------------------------------
class Instr(object):
    __slots__ = ('op', 'args', 'line', 'text')

    def __init__(self, op, args, line, text):
        self.op = op
        self.args = args      # list of ('r', idx) | ('i', value) | ('l', label) | ('k', k)
        self.line = line
        self.text = text


class Program(object):
    def __init__(self):
        self.name = None
        self.params = []        # register indices
        self.instrs = []        # all instructions in layout order
        self.labels = {}        # label -> index of first instruction
        self.label_lines = {}   # label -> source line number
        self.block_labels = []  # labels in layout order
        self.block_of = []      # for each instruction index, its block label


def _parse_operand(kind, tok, line):
    if kind == 'd':
        if not REG_RE.match(tok):
            raise KirError("expected a register (v0, v1, ...) but found '%s'" % tok, line)
        return ('r', int(tok[1:]))
    if kind == 's':
        if REG_RE.match(tok):
            return ('r', int(tok[1:]))
        if LIT_RE.match(tok):
            return ('i', parse_literal_raw(tok, line) & MASK)
        raise KirError("expected a register or an integer literal but found '%s'" % tok, line)
    if kind == 'i':
        return ('i', parse_literal_raw(tok, line) & MASK)
    if kind == 'k':
        if REG_RE.match(tok):
            raise KirError("the last operand of addsh must be a literal in 0..31, not a register", line)
        n = parse_literal_raw(tok, line)
        if n < 0 or n > 31:
            raise KirError("shift amount of addsh must be a literal in 0..31, found '%s'" % tok, line)
        return ('k', n)
    if kind == 'L':
        if not NAME_RE.match(tok) or REG_RE.match(tok):
            raise KirError("expected a label name but found '%s'" % tok, line)
        return ('l', tok)
    raise AssertionError(kind)


def parse_program(text):
    prog = Program()
    seen_func = False
    blocks = []                 # list of (label, line, [Instr])
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.split(';', 1)[0].strip()
        if not line:
            continue
        m = FUNC_RE.match(line)
        if m:
            if seen_func:
                raise KirError("only one 'func' header is allowed", lineno)
            if blocks:
                raise KirError("'func' header must come before the first label", lineno)
            seen_func = True
            prog.name = m.group(1)
            plist = m.group(2).strip()
            params = []
            if plist:
                for tok in [t.strip() for t in plist.split(',')]:
                    if not REG_RE.match(tok):
                        raise KirError("parameter '%s' is not a register" % tok, lineno)
                    idx = int(tok[1:])
                    if idx in params:
                        raise KirError("parameter '%s' is listed twice" % tok, lineno)
                    params.append(idx)
            if len(params) > MAX_PARAMS:
                raise KirError("at most %d parameters are allowed" % MAX_PARAMS, lineno)
            prog.params = params
            continue
        if not seen_func:
            raise KirError("expected 'func name(params)' as the first statement", lineno)
        m = LABEL_RE.match(line)
        if m:
            name = m.group(1)
            if REG_RE.match(name):
                raise KirError("label '%s' looks like a register name" % name, lineno)
            if name in prog.label_lines:
                raise KirError("label '%s' is defined twice (first on line %d)" % (name, prog.label_lines[name]), lineno)
            prog.label_lines[name] = lineno
            blocks.append((name, lineno, []))
            continue
        parts = line.split(None, 1)
        op = parts[0]
        if op not in SIGS:
            if op.endswith(':'):
                raise KirError("a label must be alone on its line", lineno)
            raise KirError("unknown instruction '%s'" % op, lineno)
        if not blocks:
            raise KirError("instruction outside of a block (write a label first)", lineno)
        rest = parts[1].strip() if len(parts) > 1 else ''
        toks = [t.strip() for t in rest.split(',')] if rest else []
        sig = SIGS[op]
        if len(toks) != len(sig):
            raise KirError("'%s' takes %d operand(s), found %d" % (op, len(sig), len(toks)), lineno)
        args = []
        for kind, tok in zip(sig, toks):
            if tok == '':
                raise KirError("empty operand in '%s'" % line, lineno)
            args.append(_parse_operand(kind, tok, lineno))
        blocks[-1][2].append(Instr(op, args, lineno, op + (' ' + ', '.join(toks) if toks else '')))
    if not seen_func:
        raise KirError("missing 'func name(params)' header")
    if not blocks:
        raise KirError("the function has no blocks")
    total = 0
    for label, lineno, instrs in blocks:
        if not instrs:
            raise KirError("block '%s' is empty" % label, lineno)
        for ins in instrs[:-1]:
            if ins.op in TERMINATORS:
                raise KirError("'%s' ends the block, but more instructions follow it" % ins.op, ins.line)
        if instrs[-1].op not in TERMINATORS:
            raise KirError("block '%s' must end with jmp, br, ret or trap" % label, instrs[-1].line)
        total += len(instrs)
    if total > MAX_INSTRS:
        raise KirError("program has %d instructions; the limit is %d" % (total, MAX_INSTRS))
    for label, lineno, instrs in blocks:
        prog.labels[label] = len(prog.instrs)
        prog.block_labels.append(label)
        for ins in instrs:
            prog.instrs.append(ins)
            prog.block_of.append(label)
    for ins in prog.instrs:
        for kind, val in ins.args:
            if kind == 'l' and val not in prog.labels:
                raise KirError("jump to undefined label '%s'" % val, ins.line)
    return prog


def decode_text(data):
    """Accept UTF-8, UTF-8 with BOM, and UTF-16 with BOM."""
    if data.startswith(b'\xef\xbb\xbf'):
        enc = 'utf-8-sig'
    elif data.startswith(b'\xff\xfe') or data.startswith(b'\xfe\xff'):
        enc = 'utf-16'
    else:
        enc = 'utf-8'
    return data.decode(enc)


def read_text(path):
    with open(path, 'rb') as f:
        return decode_text(f.read())


MACHINE_KEYS = [
    ('issue_width', 1), ('mem_ports', 1), ('registers', 4), ('reg_spill_penalty', 0),
    ('taken_branch_penalty', 0), ('icache_size', 1), ('icache_penalty', 0),
    ('lat_alu', 1), ('lat_mul', 1), ('lat_div', 1), ('lat_load', 1), ('lat_mac', 1),
    ('lat_addsh', 1), ('fused_mac', 0), ('fused_addsh', 0),
]
MACHINE_MAX = 1000000


def load_machine(path):
    try:
        lines = read_text(path).splitlines()
    except (IOError, OSError, UnicodeDecodeError) as e:
        raise KirError("cannot read machine config %s: %s" % (path, e))
    known = dict(MACHINE_KEYS)
    mc = {}
    for lineno, raw in enumerate(lines, 1):
        line = raw.split('#', 1)[0].strip()
        if not line:
            continue
        if '=' not in line:
            raise KirError("%s:%d: expected 'key = value'" % (path, lineno))
        key, val = [t.strip() for t in line.split('=', 1)]
        if key not in known:
            raise KirError("%s:%d: unknown key '%s'" % (path, lineno, key))
        if key in mc:
            raise KirError("%s:%d: key '%s' given twice" % (path, lineno, key))
        if not re.match(r'^[0-9]+$', val):
            raise KirError("%s:%d: value of '%s' must be a non-negative integer" % (path, lineno, key))
        n = int(val)
        if n < known[key] or n > MACHINE_MAX:
            raise KirError("%s:%d: value of '%s' must be in %d..%d" % (path, lineno, key, known[key], MACHINE_MAX))
        if key.startswith('fused_') and n > 1:
            raise KirError("%s:%d: '%s' must be 0 or 1" % (path, lineno, key))
        mc[key] = n
    for key, _ in MACHINE_KEYS:
        if key not in mc:
            raise KirError("%s: missing key '%s'" % (path, key))
    return mc


def check_machine_features(prog, mc):
    """Raise KirError if the program uses a fused op that the machine does not have."""
    for ins in prog.instrs:
        if ins.op == 'mac' and not mc['fused_mac']:
            raise KirError("'mac' is not available on this machine (fused_mac = 0)", ins.line)
        if ins.op == 'addsh' and not mc['fused_addsh']:
            raise KirError("'addsh' is not available on this machine (fused_addsh = 0)", ins.line)
