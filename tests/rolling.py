"""Check rolling memory reuse, alias rejection and zero-trip/trapping inputs."""

import argparse
from collections import Counter
from pathlib import Path
import random
import subprocess
import sys
import tempfile

from stress import MACHINE_VARIANTS


def source(rng, number, coefficient=1, stride=1, start=0, base=20, variant="rolling"):
    regs = [f"v{r}" for r in rng.sample(range(20, 900), 8)]
    n, i, condition, a, b, left, right, total = regs
    labels = [f"case_{number}_{suffix}" for suffix in ("entry", "head", "body", "done")]
    entry, head, body, done = labels
    init = f"and {i}, v1, 3" if variant == "unknown_initial" else f"const {i}, {start}"
    setup = [f"and {n}, v0, 15", init, f"const {total}, 0", "vstore 7, v1", f"jmp {head}"]
    if variant == "readonly" or variant == "invariant_store":
        coefficient = 0
    ops = [f"mul {a}, {i}, {coefficient}", f"add {a}, {a}, {base}",
           f"add {b}, {a}, {coefficient * stride}"]
    if variant == "carried_address":
        setup.insert(-1, f"const {a}, {base}")
        ops = [f"add {b}, {a}, {stride}"]
    if variant == "prior_alias":
        ops += [f"store {a}, v1"]
    if variant == "overwrite_address":
        left = a
    ops += [f"load {left}, {a}", f"add {total}, {total}, {left}"]
    if variant not in ("readonly", "invariant_store", "no_supplier"):
        ops += [f"load {right}, {b}", f"add {total}, {total}, {right}"]
    if variant == "invariant_store" or variant == "supplier_store":
        ops += [f"store {b}, {total}"]
    if variant == "late_unknown_store":
        ops += [f"store v1, {total}"]
    if variant == "volatile":
        ops += [f"vload {right}, 7", f"vstore 8, {right}"]
    if variant == "before_trap":
        ops += [f"div {right}, {total}, v1"]
    if variant == "carried_address":
        ops += [f"add {a}, {a}, {stride}"]
    ops += [f"store 700, {total}", f"add {i}, {i}, {stride}", f"jmp {head}"]
    blocks = {entry: setup, head: [f"lt {condition}, {i}, {n}", f"br {condition}, {body}, {done}"],
              body: ops, done: [f"ret {total}"]}
    rest = labels[1:]
    rng.shuffle(rest)
    return "func generated(v0, v1)\n" + "".join(
        label + ":\n  " + "\n  ".join(blocks[label]) + "\n" for label in [entry, *rest])


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
    from src.optimizer import PURE, render_canonical
    from src.rolling import reuse_loop_loads

    default = reference.load_machine(kit / "machines/machine_default.cfg")
    machines = {path.stem: reference.load_machine(path) for path in sorted((kit / "machines").glob("*.cfg"))}
    machines.update({name: default | values for name, values in MACHINE_VARIANTS.items()})
    rng = random.Random(481872)
    cases = [dict(coefficient=c, stride=s, start=i) for c in (-1, 1, 2) for s in (1, 2) for i in (0, 1)]
    cases += [dict(base=base, variant=variant) for base in (20, 3072)
              for variant in ("readonly", "invariant_store", "supplier_store", "overwrite_address", "before_trap")]
    cases += [dict(variant=variant) for variant in ("prior_alias", "late_unknown_store", "volatile", "no_supplier", "unknown_initial", "carried_address")]
    cases += [dict(base=4096), dict(base=4095), dict(base=-1)]
    outcomes, changed_outcomes = Counter(), Counter()
    selected_pairs = 0
    changed_zero_trips = 0
    comparisons = 0
    with tempfile.TemporaryDirectory(prefix="oxygen-rolling-") as folder:
        work = Path(folder)
        source_path, output_path = work / "input.kir", work / "output.kir"
        for name, machine in machines.items():
            (work / f"{name}.cfg").write_text("".join(f"{key} = {value}\n" for key, value in machine.items()))
        for number, settings in enumerate(cases):
            text = source(rng, number, **settings)
            source_path.write_text(text)
            original = reference.compile_program(reference.load_program(source_path))
            words = [0, 1, 2, 3, 7, 15, 16, 31, 0x80000000, 0xFFFFFFFF, *[rng.getrandbits(32) for _ in range(14)]]
            arguments = [[word, (0, 1, 4096, 0xFFFFFFFF, 0x80000000, 21)[index % 6]] for index, word in enumerate(words)]
            segments = [(0, [rng.getrandbits(32) for _ in range(800)]), (3072, [7, 11, 13, 17]), (4095, [19])]
            before = [reference.execute(original, values, segments, {7: [11, 13]}, 10_000) for values in arguments]
            for name, machine in machines.items():
                parsed = parse_program(text)
                starts = [parsed.labels[label] for label in parsed.block_labels]
                blocks = {label: parsed.instrs[start:end] for label, start, end in zip(
                    parsed.block_labels, starts, [*starts[1:], len(parsed.instrs)])}
                selected = reuse_loop_loads(blocks, parsed.block_labels, parsed.params, machine, PURE)
                rejected = settings.get("variant") in ("prior_alias", "late_unknown_store", "volatile", "no_supplier", "unknown_initial", "carried_address") or settings.get("base") in (-1, 4096)
                if rejected and selected:
                    raise RuntimeError(f"unsafe proof accepted: case {number}, {name}, {settings}")
                selected_pairs += selected
                output_path.write_text(render_canonical(parsed, blocks, parsed.block_labels, {}))
                direct = reference.compile_program(reference.load_program(output_path))
                subprocess.run([Path(__file__).resolve().parents[1] / "kopt", source_path,
                                "--machine", work / f"{name}.cfg", "-o", output_path],
                               check=True, capture_output=True, timeout=5)
                integrated_program = reference.load_program(output_path)
                reference.check_machine_features(integrated_program, machine)
                integrated = reference.compile_program(integrated_program)
                for values, original_result in zip(arguments, before):
                    if original_result.status == "TIMEOUT":
                        raise RuntimeError("generated reference did not terminate")
                    for label, compiled in (("direct", direct), ("integrated", integrated)):
                        result = reference.execute(compiled, values, segments, {7: [11, 13]}, 10_000)
                        difference = reference.first_difference(original_result, result)
                        if difference:
                            raise RuntimeError(f"case {number}, {name}, {values}, {label}: {difference}\n{text}")
                        comparisons += 1
                    outcome = original_result.status if original_result.status == "RET" else original_result.value
                    outcomes[outcome] += 1
                    if selected:
                        changed_outcomes[outcome] += 1
                        changed_zero_trips += (values[0] & 15) <= settings.get("start", 0)
    if not selected_pairs or not changed_zero_trips or not all(changed_outcomes[k] for k in ("RET", "div_by_zero", "bad_address")):
        raise RuntimeError("rolling tests did not exercise transformed zero trips, returns and both implicit traps")
    print(f"{len(cases)} rolling-memory cases × {len(machines)} machines × 24 inputs: {comparisons:,} direct/integrated matches; "
          f"{selected_pairs} transformed pairs, {changed_zero_trips} transformed zero-trip checks; "
          f"{dict(outcomes)}; transformed outcomes {dict(changed_outcomes)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
