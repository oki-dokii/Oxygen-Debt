"""Compare kopt with unoptimized KIR using an external COMP10 starter kit."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
import subprocess
import sys
import tempfile
import time


@dataclass(frozen=True)
class Sample:
    program: str
    machine: str
    seconds: float
    before: int | None
    after: int | None


def compare(kir, optimizer, program, machine, output):
    try:
        original = kir.load_program(program)
        config = kir.load_machine(machine)
        kir.check_machine_features(original, config)
        inputs = kir.load_input(program.with_suffix(".in"), len(original.params))
        command = [optimizer, program, "--machine", machine, "-o", output]
        profile = program.with_suffix(".prof")
        if profile.is_file():
            command.extend(["--profile", profile])
        timeout = 30 if len(original.instrs) >= 100_000 else 5
        start = time.perf_counter()
        run = subprocess.run(command, cwd=output.parent, capture_output=True, timeout=timeout)
        seconds = time.perf_counter() - start
        if run.returncode:
            raise RuntimeError(run.stderr.decode(errors="replace").strip() or f"exit {run.returncode}")

        optimized = kir.load_program(output)
        kir.check_machine_features(optimized, config)
        if len(original.params) != len(optimized.params):
            raise RuntimeError("optimizer changed the number of parameters")
        before, after = map(kir.compile_program, (original, optimized))
        before_run = kir.execute(
            before, inputs.args, inputs.segments, inputs.vin, kir.DEFAULT_MAX_STEPS, want_trace=True,
        )
        if before_run.status == "TIMEOUT":
            return Sample(program.stem, machine.stem, seconds, None, None)
        after_run = kir.execute(
            after, inputs.args, inputs.segments, inputs.vin, 20 * before_run.steps + 1000, want_trace=True,
        )
        difference = kir.first_difference(before_run, after_run)
        if difference:
            raise RuntimeError(difference)
        return Sample(
            program.stem, machine.stem, seconds,
            kir.time_trace(before, before_run.trace, config),
            kir.time_trace(after, after_run.trace, config),
        )
    except (OSError, RuntimeError, subprocess.TimeoutExpired, kir.KirError) as error:
        raise RuntimeError(f"{machine.stem}/{program.stem}: {error}") from error


def select_files(folder, extension, names):
    files = sorted(folder.glob(f"*.{extension}"))
    if not files:
        raise ValueError(f"No .{extension} files in {folder}")
    unknown = set(names) - {path.stem for path in files}
    if unknown:
        raise ValueError(f"Unknown .{extension} names: {', '.join(sorted(unknown))}")
    return [path for path in files if not names or path.stem in names]


def print_results(rows, machines, details):
    for machine in machines:
        results = [row for row in rows if row.machine == machine.stem]
        compared = [row for row in results if row.before is not None]
        improved = sum(row.after < row.before for row in compared)
        slower = sum(row.after > row.before for row in compared)
        tied = len(compared) - improved - slower
        before = sum(row.before for row in compared)
        after = sum(row.after for row in compared)
        print(f"{machine.stem}: {improved} improved, {tied} tied, {slower} slower, "
              f"{len(results) - len(compared)} skipped | {before:,} -> {after:,} cycles")
        for row in compared:
            if details or row.after > row.before:
                print(f"  {row.program}: {row.before:,} -> {row.after:,}")
    print(f"{len(rows)} samples, max kopt wall time {max(row.seconds for row in rows):.3f}s")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kit", type=Path, help="path to the official Compilers/COMP10 directory")
    parser.add_argument("--optimizer", type=Path, default=Path(__file__).resolve().parents[1] / "kopt")
    parser.add_argument("--program", action="append", default=[], help="limit to this program stem")
    parser.add_argument("--machine", action="append", default=[], help="limit to this machine stem")
    parser.add_argument("--jobs", type=int, default=1, help="number of simultaneous samples")
    parser.add_argument("--details", action="store_true", help="print cycle counts for every sample")
    args = parser.parse_args()
    if args.jobs < 1:
        parser.error("--jobs must be positive")
    kit = args.kit.resolve()
    if not (kit / "kirlib.py").is_file():
        parser.error(f"No official kirlib.py in {kit}")

    sys.dont_write_bytecode = True
    sys.path.insert(0, str(kit))
    import kirlib as kir

    try:
        programs = select_files(kit / "bench", "kir", args.program)
        machines = select_files(kit / "machines", "cfg", args.machine)
        optimizer = args.optimizer.resolve()
        with tempfile.TemporaryDirectory(prefix="oxygen-bench-") as directory:
            output_dir = Path(directory)
            with ThreadPoolExecutor(max_workers=args.jobs) as pool:
                pending = [
                    pool.submit(compare, kir, optimizer, program, machine, output_dir / f"{i}.kir")
                    for i, (program, machine) in enumerate(
                        (program, machine) for machine in machines for program in programs
                    )
                ]
                rows = [result.result() for result in pending]
        print_results(rows, machines, args.details)
        return 0
    except (RuntimeError, ValueError) as error:
        print(f"benchmark: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
