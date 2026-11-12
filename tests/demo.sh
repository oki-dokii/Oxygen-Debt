#!/bin/sh
set -eu

if [ "$#" -ne 1 ]; then
    printf 'Usage: sh tests/demo.sh /path/to/LLH-26/Compilers/COMP10\n' >&2
    exit 2
fi

repo=$(CDPATH= cd "$(dirname "$0")/.." && pwd)
kit=$(CDPATH= cd "$1" && pwd)
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
export PYTHONDONTWRITEBYTECODE=1
cd "$work"

"$repo/build.sh"
cp "$kit/bench/sum_sq.kir" "$kit/bench/sum_sq.in" .

for machine in machine_default machine_no_fused; do
    config="$kit/machines/$machine.cfg"
    printf '\n=== sum_sq on %s ===\n' "$machine"
    "$repo/kopt" sum_sq.kir --machine "$config" -o optimized.kir
    python3 "$kit/kvalidate" sum_sq.kir --machine "$config"
    python3 "$kit/kvalidate" optimized.kir --against sum_sq.kir --machine "$config"
    printf '\nOptimized KIR\n'
    cat optimized.kir
    printf '\nOriginal result and cycles\n'
    python3 "$kit/ksim" sum_sq.kir --machine "$config" --input sum_sq.in
    printf '\nOptimized result and cycles\n'
    python3 "$kit/ksim" optimized.kir --machine "$config" --input sum_sq.in
done

for name in collatz matmul4 matrix_add4 transpose8 sieve bounds_trap branchy_select stencil3 popcount bit_reverse crc_bitwise nested_invariant adler32 fletcher16; do
    printf '\n=== %s on machine_default ===\n' "$name"
    cp "$kit/bench/$name.kir" "$kit/bench/$name.in" .
    config="$kit/machines/machine_default.cfg"
    "$repo/kopt" "$name.kir" --machine "$config" -o "$name.optimized.kir"
    python3 "$kit/kvalidate" "$name.kir" --machine "$config"
    python3 "$kit/kvalidate" "$name.optimized.kir" --against "$name.kir" --machine "$config"
    printf '\nOriginal result and cycles\n'
    python3 "$kit/ksim" "$name.kir" --machine "$config" --input "$name.in"
    printf '\nOptimized result and cycles\n'
    python3 "$kit/ksim" "$name.optimized.kir" --machine "$config" --input "$name.in"
done

printf '\n=== Stores before a division trap ===\n'
cp "$kit/bench/store_then_div_trap.kir" .
printf 'args 100 0\n' > divide_by_zero.in
config="$kit/machines/machine_default.cfg"
"$repo/kopt" store_then_div_trap.kir --machine "$config" -o trap_optimized.kir
python3 "$kit/kvalidate" store_then_div_trap.kir --machine "$config"
python3 "$kit/kvalidate" trap_optimized.kir --against store_then_div_trap.kir \
    --machine "$config" --input divide_by_zero.in --random 0
for program in store_then_div_trap.kir trap_optimized.kir; do
    python3 "$kit/ksim" "$program" --machine "$config" --input divide_by_zero.in --verbose
done
