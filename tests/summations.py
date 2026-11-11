"""Check bounded-loop formulas against the independent organizer interpreter."""

import argparse
from collections import Counter
from pathlib import Path
import random
import subprocess
import sys
import tempfile

from stress import MACHINE_VARIANTS


def make_case(rng, index, degree, coefficient, offset, initial, modulus=None, reject=None):
    registers = rng.sample(range(20, 900), 8)
    bound, acc, counter, cond, term, temp, carried, parameter = [f"v{r}" for r in registers]
    labels = [f"block_{index}_{i}" for i in range(4)]
    entry, head, body, done = labels
    mask = 511 if reject == "large_bound" else 255
    init_index = 1 if reject == "offset_index" else 0
    step = 2 if reject == "stride" else 1
    setup = [f"and {bound}, v0, {mask}", f"mov {acc}, v1" if initial is None else f"const {acc}, {initial}",
             f"const {counter}, {init_index}"]
    if reject == "carried":
        setup.append(f"const {carried}, 0")
    setup += ["store 0, v1", "vstore 3, v1", f"jmp {head}"]
    operations = [f"const {term}, 1"] if degree == 0 else [f"mov {term}, {counter}"]
    for _ in range(degree - 1):
        operations.append(f"mul {term}, {term}, {counter}")
    operations += [f"mul {term}, {term}, {coefficient}", f"add {term}, {term}, {offset}"]
    if reject == "carried":
        operations += [f"add {term}, {term}, {carried}", f"add {carried}, {carried}, 1"]
    operations.append(f"add {acc}, {acc}, {term}")
    if modulus is not None:
        operations.append(f"mod {acc}, {acc}, {modulus}")
    if reject == "effects":
        operations.append(f"vstore 7, {acc}")
    if reject == "memory":
        operations.append(f"load {temp}, {parameter}")
    operations += [f"add {counter}, {counter}, {step}", f"jmp {head}"]
    blocks = {entry: setup, head: [f"lt {cond}, {counter}, {bound}", f"br {cond}, {body}, {done}"],
              body: operations, done: [f"ret {acc}"]}
    rest = labels[1:]
    rng.shuffle(rest)
    source = f"func generated(v0, v1, {parameter})\n" + "".join(
        label + ":\n  " + "\n  ".join(blocks[label]) + "\n" for label in [entry, *rest])
    return source, head, mask, init_index, step


def run(kir, kit, optimizer, work):
    default = kir.load_machine(kit / "machines/machine_default.cfg")
    machines = {path.stem: kir.load_machine(path) for path in sorted((kit / "machines").glob("*.cfg"))}
    machines.update({name: default | values for name, values in MACHINE_VARIANTS.items()})
    for name, values in machines.items():
        (work / f"{name}.cfg").write_text("".join(f"{key} = {value}\n" for key, value in values.items()))
    rng = random.Random(582719)
    cases = [
        (degree, coefficient, offset, initial, modulus, None)
        for degree in range(4)
        for coefficient, offset, initial, modulus in (
            (1, 0, 0, None), (-3, 7, -1, None), (5, -9, None, None), (1, 3, 0, 1009),
        )
    ]
    cases += [
        (degree, 1, 0, 0, None, why)
        for degree in (1, 2) for why in ("large_bound", "offset_index", "stride", "carried", "effects", "memory")
    ]
    cases += [(2, 1, 0, 1009, 1009, "initial_modulus"), (2, -1, 0, 0, 1009, "negative_modulus_input"),
              (3, 1000, 0, 0, 1009, "modulus_overflow")]
    outcomes = Counter()
    program, output = work / "in.kir", work / "out.kir"
    for index, (degree, coefficient, offset, initial, modulus, reject) in enumerate(cases):
        source, head, mask, start, stride = make_case(
            rng, index, degree, coefficient, offset, initial, modulus, reject)
        program.write_text(source)
        original = kir.compile_program(kir.load_program(program))
        counts = [*range(256), 256, 511, kir.MASK, 0x80000000]
        inputs = [(n, (0, 1, kir.MASK, 0x80000000)[n % 4], 4096 if n % 2 else 0) for n in counts]
        references = [kir.execute(original, args, [(0, [19])], {}, 20_000) for args in inputs]
        for args, result in zip(inputs, references):
            if reject in ("carried", "effects", "memory"):
                continue
            expected = args[1] if initial is None else initial & kir.MASK
            for counter in range(start, args[0] & mask, stride):
                expected = (expected + coefficient * counter ** degree + offset) & kir.MASK
                if modulus is not None:
                    signed = expected if expected < 0x80000000 else expected - (1 << 32)
                    expected = (signed % modulus if signed >= 0 else -((-signed) % modulus)) & kir.MASK
            if result.status != "RET" or result.value != expected:
                raise RuntimeError(f"test generator and arithmetic oracle disagree: case {index}, {args}")
        for name, machine in machines.items():
            command = [optimizer, program, "--machine", work / f"{name}.cfg", "-o", output]
            subprocess.run(command, check=True, capture_output=True, timeout=5)
            parsed = kir.load_program(output)
            kir.check_machine_features(parsed, machine)
            if reject is None and head in parsed.labels:
                raise RuntimeError(f"expected a proven formula: case {index}, machine {name}\n{output.read_text()}")
            if reject in ("initial_modulus", "negative_modulus_input", "modulus_overflow") and head not in parsed.labels:
                raise RuntimeError(f"unsafe modular proof accepted: case {index}, machine {name}")
            optimized = kir.compile_program(parsed)
            for args, before in zip(inputs, references):
                after = kir.execute(optimized, args, [(0, [19])], {}, 20_000)
                difference = kir.first_difference(before, after)
                if before.status == "TIMEOUT" or difference:
                    raise RuntimeError(f"case {index}, machine {name}, args {args}: {difference}\n{source}")
                outcomes[before.status if before.status == "RET" else before.value] += 1
    print(f"{len(cases)} generated summations × {len(machines)} machines × 260 inputs: "
          f"{sum(outcomes.values()):,} matches; {dict(outcomes)}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kit", type=Path)
    parser.add_argument("--optimizer", type=Path, default=Path(__file__).resolve().parents[1] / "kopt")
    args = parser.parse_args()
    kit = args.kit.resolve()
    if not (kit / "kirlib.py").is_file():
        parser.error("provide the organizer's COMP10 directory")
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(kit))
    import kirlib as kir

    try:
        with tempfile.TemporaryDirectory(prefix="oxygen-summations-") as directory:
            run(kir, kit, args.optimizer.resolve(), Path(directory))
    except (RuntimeError, subprocess.SubprocessError, kir.KirError) as error:
        print(f"summations: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
