"""Differentially test fresh KIR programs on supplied and synthetic machines."""

import argparse
from collections import Counter
from pathlib import Path
import random
import subprocess
import sys
import tempfile


MACHINE_VARIANTS = {
    "tiny": dict(issue_width=1, registers=4, reg_spill_penalty=17,
                 icache_size=1, icache_penalty=3, fused_mac=0, fused_addsh=0),
    "slow_alu": dict(lat_alu=7, lat_mul=1, lat_load=1, lat_mac=12,
                     lat_addsh=15, fused_mac=1, fused_addsh=1),
    "wide": dict(issue_width=8, mem_ports=3, registers=16,
                 taken_branch_penalty=19, lat_load=20, fused_mac=0, fused_addsh=1),
}

# Equal and unequal pointers, zero divisors, signed overflow, data/scratch
# boundaries, and unsigned out-of-bounds addresses. Both sides of the branch run.
ARGUMENTS = (
    (0, 0, 1, 0), (0, 1, -1, 1), (1, 0, 0, 2), (3071, 3071, 3, 3),
    (3072, 3071, -3, 4), (4095, 4095, 1, 5), (4095, 4096, 0, 6),
    (4096, 0, 0, 7), (-1, -1, 1, 0), (3071, -1, -1, 1),
    (1, 1, -2147483648, 0), (0, 3072, 0, -1),
)


def mixed_ops(rng):
    """Use small register sets, frequent overwrites, and edge literals."""
    for _ in range(rng.randint(3, 9)):
        op = rng.choice(("add", "sub", "mul", "and", "or", "xor", "lt", "eq", "shr", "shl"))
        dest = rng.choice(("v5", "v8", "v10"))
        left = rng.choice(("v5", "v8", "v10", "v3"))
        right = rng.choice(("v5", "v8", "v10", "0", "1", "31", "32", "33", "-1", "0x80000000"))
        yield f"{op} {dest}, {left}, {right}"


def make_program(rng, index):
    if index % 2 == 0:
        middle = (
            ["store v1, v6", "load v8, v4", "mov v10, v8", "vload v8, 7", "load v8, v4"],
            ["store v4, v6", "load v10, v0", "vload v6, 7", "vload v10, 7", "load v8, v4"],
            ["store 3072, v6", "load v10, 3072", "store 3071, v5", "load v8, 3072"],
            ["load v4, v4", "load v10, v4", "vload v10, 7", "load v8, v4"],
        )[index // 2 % 4]
        divop = rng.choice(("div", "mod"))
        blocks = {"entry": [
            "store 2, v3", "mov v4, v0", "load v5, v4", "vstore 7, v5", "vload v6, 7",
            *middle, "vstore 8, v8", f"{divop} v10, v10, v2",
            *mixed_ops(rng), "add v5, v5, v8", "add v5, v5, v10", "ret v5",
        ]}
        profile = ""
    else:
        blocks = {
            "entry": ["and v6, v3, 7", "br v3, right, left"],
            "left": ["add v5, v2, v0", "store 3072, v0", "jmp join"],
            "right": ["sub v5, v2, v1", "store 3072, v1", "jmp join"],
            "join": ["load v8, 3072", "br v6, body, done"],
            "body": ["vload v10, 7", *mixed_ops(rng), "mul v9, v5, 4", "add v5, v9, v10",
                     "sub v6, v6, 1", "br v6, body, done"],
            "done": ["add v5, v5, v8", "store 3071, v5", "vstore 7, v5", "ret v5"],
        }
        profile = "edge entry left 10000\nedge entry right 1\nedge body done 500\nedge body body 1\n"
    rest = [label for label in blocks if label != "entry"]
    rng.shuffle(rest)
    source = "func stress(v0, v1, v2, v3)\n"
    source += "".join(label + ":\n  " + "\n  ".join(blocks[label]) + "\n" for label in ["entry", *rest])
    return source, profile


def make_inputs(kir, rng):
    for args in ARGUMENTS:
        word = rng.choice((0, 1, 3071, 3072, 4095, 4096, kir.MASK, 0x80000000))
        yield kir.Inputs(list(args), [(0, [word, word ^ 1]), (3071, [word, 77]), (4095, [word])],
                         {7: [rng.getrandbits(32) for _ in range(rng.randrange(4))]})


def run_suite(kir, kit, optimizer, work, count, seed):
    rng = random.Random(seed)
    default = kir.load_machine(kit / "machines/machine_default.cfg")
    machines = {"default": default}
    machines.update({name: default | config for name, config in MACHINE_VARIANTS.items()})
    for name, config in machines.items():
        (work / f"{name}.cfg").write_text("".join(f"{key} = {value}\n" for key, value in config.items()))

    program, prof, output = (work / name for name in ("stress.kir", "stress.prof", "out.kir"))
    endings = Counter()
    for index in range(count):
        source, profile = make_program(rng, index)
        program.write_text(source)
        prof.write_text(profile)
        original = kir.compile_program(kir.load_program(program))
        inputs = list(make_inputs(kir, rng))
        results = [kir.execute(original, case.args, case.segments, case.vin, 1000) for case in inputs]
        if any(result.status == "TIMEOUT" for result in results):
            raise RuntimeError(f"generator produced a nonterminating case: seed={seed}, program={index}")
        for name, config in machines.items():
            command = [optimizer, program, "--machine", work / f"{name}.cfg", "-o", output]
            if profile:
                command.extend(["--profile", prof])
            where = f"seed={seed}, program={index}, machine={name}"
            try:
                run = subprocess.run(command, cwd=work, capture_output=True, text=True, timeout=5)
                if run.returncode:
                    raise RuntimeError(run.stderr.strip() or f"kopt exited {run.returncode}")
                optimized = kir.load_program(output)
                kir.check_machine_features(optimized, config)
                if len(optimized.params) != original.nparams:
                    raise RuntimeError("optimizer changed the number of parameters")
                optimized = kir.compile_program(optimized)
                for case, before in zip(inputs, results):
                    after = kir.execute(optimized, case.args, case.segments, case.vin, 1000)
                    difference = kir.first_difference(before, after)
                    if difference:
                        raise RuntimeError(f"{difference}\n{kir.format_input(case)}")
                    endings[before.status if before.status == "RET" else before.value] += 1
            except (RuntimeError, OSError, subprocess.TimeoutExpired, kir.KirError) as error:
                raise RuntimeError(f"{where}: {error}\n{source}\n{profile}") from error
    outcomes = ", ".join(f"{kind}={total:,}" for kind, total in sorted(endings.items()))
    print(f"{count} generated programs × {len(machines)} machines, "
          f"{sum(endings.values()):,} comparisons passed (seed {seed}; {outcomes})")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kit", type=Path, help="path to the official Compilers/COMP10 directory")
    parser.add_argument("--optimizer", type=Path, default=Path(__file__).resolve().parents[1] / "kopt")
    parser.add_argument("--programs", type=int, default=100)
    parser.add_argument("--seed", type=int, default=60723)
    args = parser.parse_args()
    kit = args.kit.resolve()
    if not (kit / "kirlib.py").is_file() or args.programs < 1:
        parser.error("provide a valid kit directory and positive program count")
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(kit))
    import kirlib as kir

    with tempfile.TemporaryDirectory(prefix="oxygen-stress-") as directory:
        try:
            run_suite(kir, kit, args.optimizer.resolve(), Path(directory), args.programs, args.seed)
        except RuntimeError as error:
            print(f"stress: {error}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
