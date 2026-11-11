"""Exercise finite-domain proofs, generated lookup code, and rejection cases."""

import argparse
from collections import Counter
from pathlib import Path
import random
import subprocess
import sys
import tempfile

from stress import MACHINE_VARIANTS


def loop_source(mask, copied=False):
    prefix = f"  and v0, v0, {mask}\n"
    if copied:
        prefix = f"  and v2, v0, {mask}\n  add v0, v2, 1\n  sub v0, v0, 1\n"
    return (
        "func kernel(v0)\nentry:\n" + prefix
        + "  and v1, v0, 15\n  const v2, 0\n  const v3, 0\n  jmp head\n"
        "head:\n  lt v4, v3, v1\n  br v4, body, done\n"
        "body:\n  xor v2, v2, v3\n  mul v2, v2, 17\n  add v3, v3, 1\n  jmp head\n"
        "done:\n  xor v2, v2, v0\n  ret v2\n"
    )


def run(kir, kit, optimizer, work):
    default = kir.load_machine(kit / "machines/machine_default.cfg")
    machines = {path.stem: kir.load_machine(path) for path in sorted((kit / "machines").glob("*.cfg"))}
    machines.update({name: default | settings for name, settings in MACHINE_VARIANTS.items()})
    for name, machine in machines.items():
        (work / f"{name}.cfg").write_text("".join(f"{key} = {value}\n" for key, value in machine.items()))
    cases = [(loop_source(mask, copied), mask, False) for mask in (15, 255, 0xA5, 0x80000003)
             for copied in (False, True)]
    unsafe = [
        "func kernel(v0)\nentry:\n  and v1, v0, 15\n  add v2, v0, v1\n  ret v2\n",
        "func kernel(v0)\nentry:\n  mov v2, v0\n  and v0, v0, 15\n  add v1, v2, v0\n  ret v1\n",
        "func kernel(v0, v1)\nentry:\n  and v2, v0, 15\n  add v2, v2, v1\n  ret v2\n",
        "func kernel(v0)\nentry:\n  and v0, v0, 15\n  load v1, v0\n  ret v1\n",
        "func kernel(v0)\nentry:\n  and v0, v0, 15\n  vstore 7, v0\n  ret v0\n",
        "func kernel(v0)\nentry:\n  and v0, v0, 15\n  div v1, 7, v0\n  ret v1\n",
        "func kernel(v0)\nentry:\n  and v0, v0, 15\n  br v0, done, forever\n"
        "forever:\n  jmp forever\ndone:\n  ret v0\n",
    ]
    cases += [(source, None, True) for source in unsafe]
    rng = random.Random(294785)
    outcomes = Counter()
    program, output = work / "input.kir", work / "output.kir"
    specialized = 0
    skipped = 0
    for index, (source, mask, reject) in enumerate(cases):
        program.write_text(source)
        original_program = kir.load_program(program)
        original = kir.compile_program(original_program)
        words = [*range(256), 0x80000000, 0xFFFFFFFF, *[rng.getrandbits(32) for _ in range(30)]]
        if mask is not None:
            bits = [bit for bit in range(32) if mask & (1 << bit)]
            words += [sum(((number >> i) & 1) << bit for i, bit in enumerate(bits))
                      for number in range(1 << len(bits))]
        args = [[word] + ([rng.getrandbits(32)] if original.nparams == 2 else []) for word in words]
        references = [kir.execute(original, values, [(0, [17, 19, 23])], {}, 20_000) for values in args]
        for values, result in zip(args, references):
            if mask is None:
                continue
            masked = values[0] & mask
            expected = 0
            for counter in range(masked & 15):
                expected = ((expected ^ counter) * 17) & kir.MASK
            if result.status != "RET" or result.value != expected ^ masked:
                raise RuntimeError(f"generator and oracle disagree in case {index}, {values}")
        for name, machine in machines.items():
            subprocess.run([optimizer, program, "--machine", work / f"{name}.cfg", "-o", output],
                           check=True, capture_output=True, timeout=5)
            parsed = kir.load_program(output)
            kir.check_machine_features(parsed, machine)
            selected = "finite_entry" in parsed.labels
            if reject and selected:
                raise RuntimeError(f"unsafe finite proof accepted: case {index}, machine {name}")
            specialized += selected
            optimized = kir.compile_program(parsed)
            for values, before in zip(args, references):
                if before.status == "TIMEOUT":
                    skipped += 1
                    continue
                after = kir.execute(optimized, values, [(0, [17, 19, 23])], {}, 20_000)
                difference = kir.first_difference(before, after)
                if difference:
                    raise RuntimeError(f"case {index}, machine {name}, args {values}: {difference}\n{source}")
                outcomes[before.status if before.status == "RET" else before.value] += 1
    if not specialized:
        raise RuntimeError("no finite specialization was exercised")
    print(f"{len(cases)} finite-domain cases × {len(machines)} machines: "
          f"{sum(outcomes.values()):,} matches, {specialized} specialized pairs, "
          f"{skipped} nonterminating references skipped; {dict(outcomes)}")


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
        with tempfile.TemporaryDirectory(prefix="oxygen-finite-") as directory:
            run(kir, kit, args.optimizer.resolve(), Path(directory))
    except (RuntimeError, subprocess.SubprocessError, kir.KirError) as error:
        print(f"finite: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
