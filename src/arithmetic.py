"""Fold KIR arithmetic with 32-bit wrapping semantics."""

from operator import add, and_, eq, mul, or_, sub, xor

from .kirlib import MASK


BINARY = {
    "add": add, "sub": sub, "mul": mul, "and": and_, "or": or_, "xor": xor,
    "eq": eq, "lt": lambda a, b: (a ^ 0x80000000) < (b ^ 0x80000000),
    "shl": lambda a, b: a << (b & 31), "shr": lambda a, b: a >> (b & 31),
}
RIGHT_IDENTITY = {
    "add": 0, "sub": 0, "mul": 1, "and": MASK, "or": 0, "xor": 0,
    "shl": 0, "shr": 0,
}
COMMUTATIVE = {"add", "mul", "and", "or", "xor", "eq"}


def simplify(op, sources):
    if op == "select":
        cond, yes, no = sources
        if yes == no:
            return yes
        if cond[0] == "i":
            return yes if cond[1] else no
    if op not in BINARY:
        return None

    left, right = sources
    if left[0] == right[0] == "i":
        return ("i", int(BINARY[op](left[1], right[1])) & MASK)
    if left == right:
        if op in {"sub", "xor", "lt", "eq"}:
            return ("i", int(op == "eq"))
        if op in {"and", "or"}:
            return left
    if op in COMMUTATIVE and left[0] == "i":
        left, right = right, left
    if right[0] == "i":
        literal = right[1]
        if op in {"shl", "shr"}:
            literal &= 31
        if literal == RIGHT_IDENTITY.get(op):
            return left
        if (op in {"mul", "and"} and literal == 0) or (op == "or" and literal == MASK):
            return right
    return None
