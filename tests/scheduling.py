"""Check scheduling dependencies against the independent organizer interpreter."""

import argparse
from collections import Counter
from pathlib import Path
import random
import sys
import tempfile

from stress import MACHINE_VARIANTS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kit", type=Path)
    args = parser.parse_args()
    kit = args.kit.resolve()
    if not (kit / "kirlib.py").is_file():
        parser.error("provide the organizer's COMP10 directory")
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(kit))
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import kirlib as reference
    from src.kirlib import parse_program
    from src.optimizer import render_canonical
    from src.schedule import schedule_blocks

    default = reference.load_machine(kit / "machines/machine_default.cfg")
    machines = {path.stem: reference.load_machine(path) for path in sorted((kit / "machines").glob("*.cfg"))}
    machines.update({name: default | settings for name, settings in MACHINE_VARIANTS.items()})
    rng = random.Random(924812)
    outcomes = Counter()
    changed = 0
    with tempfile.TemporaryDirectory(prefix="oxygen-schedule-") as directory:
        original_path, optimized_path = (Path(directory) / name for name in ("in.kir", "out.kir"))
        for case in range(200):
            lines = ["func kernel(v0, v1)", "entry:"]
            # Independent work following a long operation creates useful scheduling choices.
            lines += ["  mul v2, v0, v1", "  add v3, v2, 7", "  xor v4, v0, v1"]
            for _ in range(30):
                dest = f"v{rng.randrange(7)}"
                left = f"v{rng.randrange(7)}"
                right = f"v{rng.randrange(7)}" if rng.randrange(2) else str(rng.choice([0, 1, 3, 31, 32, -1]))
                op = rng.choice(["add", "sub", "xor", "and", "or", "mul", "shl", "shr", "lt", "eq",
                                 "div", "mod", "load", "store", "select"])
                if op == "load":
                    lines.append(f"  load {dest}, {rng.choice([left, '0', '4095', '4096'])}")
                elif op == "store":
                    lines.append(f"  store {rng.choice([left, '0', '4095', '4096'])}, {right}")
                elif op == "select":
                    lines.append(f"  select {dest}, {left}, {right}, v0")
                else:
                    lines.append(f"  {op} {dest}, {left}, {right}")
            if case % 10 == 0:
                lines += ["  vload v3, 7", "  vstore 7, v3"]
            lines.append("  trap v3" if case % 7 == 0 else "  ret v3")
            if case < 20:
                lines = ["func kernel(v0, v1)", "entry:", "  mul v2, v0, v1",
                         f"  add v3, v2, {case + 1}", "  mul v4, v0, v1",
                         "  add v5, v4, 3", "  add v6, v3, v5", "  ret v6"]
            source = "\n".join(lines) + "\n"
            original_path.write_text(source)
            original = reference.compile_program(reference.load_program(original_path))
            inputs = [[a, b] for a in (0, 1, 2, 31, 0x7FFFFFFF, 0x80000000, 0xFFFFFFFF, rng.getrandbits(32))
                      for b in (0, 1, 2, 3, 31, 0x7FFFFFFF, 0x80000000, 0xFFFFFFFF)]
            references = [reference.execute(original, values, [(0, [17, 19, 23])], {7: [11]}, 1000)
                          for values in inputs]
            for name, machine in machines.items():
                program = parse_program(source)
                blocks = {"entry": program.instrs[:]}
                selected = schedule_blocks(blocks, ["entry"], program.params, machine)
                changed += selected
                if case >= 20 and case % 10 == 0 and selected:
                    raise RuntimeError("volatile block was scheduled")
                optimized_path.write_text(render_canonical(program, blocks, ["entry"], {}))
                parsed = reference.load_program(optimized_path)
                reference.check_machine_features(parsed, machine)
                optimized = reference.compile_program(parsed)
                for values, before in zip(inputs, references):
                    after = reference.execute(optimized, values, [(0, [17, 19, 23])], {7: [11]}, 1000)
                    difference = reference.first_difference(before, after)
                    if difference:
                        raise RuntimeError(f"case {case}, {name}, {values}: {difference}\n{source}")
                    outcomes[before.status if before.status == "RET" else before.value] += 1
    if not changed:
        raise RuntimeError("no schedule changed")
    print(f"200 scheduling cases × {len(machines)} machines: {sum(outcomes.values()):,} matches, "
          f"{changed} reordered pairs; {dict(outcomes)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
