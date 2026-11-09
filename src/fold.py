"""Fold arithmetic whose operands are known within a basic block."""

from operator import add, mul, sub

from .kirlib import MASK, SIGS


ARITHMETIC = {"add": add, "sub": sub, "mul": mul}


def known_value(operand, constants):
    kind, value = operand
    return value if kind == "i" else constants.get(value)


def fold_constants(program, source, machine):
    """Return edited KIR, or None when the source can pass through byte for byte."""
    constants = {}
    replacements = {}
    for index, instruction in enumerate(program.instrs):
        if program.labels[program.block_of[index]] == index:
            constants.clear()

        op = instruction.op
        if not SIGS[op].startswith("d"):
            continue

        dest = instruction.args[0][1]
        value = None
        if op in ("const", "mov"):
            value = known_value(instruction.args[1], constants)
        elif op in ARITHMETIC:
            left = known_value(instruction.args[1], constants)
            right = known_value(instruction.args[2], constants)
            if left is not None and right is not None:
                value = ARITHMETIC[op](left, right) & MASK
                if op != "mul" or machine["lat_alu"] <= machine["lat_mul"]:
                    replacements[instruction.line - 1] = f"const v{dest}, {value}"

        # KIR reads sources before writing the destination, which may alias a source.
        if value is None:
            constants.pop(dest, None)
        else:
            constants[dest] = value

    if not replacements:
        return None

    lines = source.splitlines(keepends=True)
    for index, replacement in replacements.items():
        line = lines[index]
        body = line.splitlines()[0]
        instruction, separator, comment = body.partition(";")
        indent = instruction[:len(instruction) - len(instruction.lstrip())]
        if separator:
            replacement += f" ;{comment}"
        lines[index] = indent + replacement + line[len(body):]
    return "".join(lines)
