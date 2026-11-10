import subprocess
import tempfile
import unittest
from pathlib import Path


KOPT = Path(__file__).resolve().parents[1] / "kopt"
MACHINE = """\
issue_width = 1
mem_ports = 1
registers = 4
reg_spill_penalty = 0
taken_branch_penalty = 0
icache_size = 64
icache_penalty = 0
lat_alu = 1
lat_mul = 2
lat_div = 4
lat_load = 2
lat_mac = 2
lat_addsh = 1
fused_mac = 0
fused_addsh = 0
"""


class KoptTests(unittest.TestCase):
    def run_kopt(self, source, machine=MACHINE, extra_args=(), profile=None):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            (work / "in.kir").write_bytes(source)
            (work / "machine.cfg").write_text(machine, encoding="utf-8")
            if profile is not None:
                (work / "branch.prof").write_text(profile, encoding="utf-8")
                extra_args = (*extra_args, "--profile", "branch.prof")
            result = subprocess.run(
                [KOPT, "in.kir", "--machine", "machine.cfg", *extra_args, "-o", "out.kir"],
                cwd=work,
                capture_output=True,
            )
            output = work / "out.kir"
            return result, output.read_bytes() if output.exists() else None

    def test_folding_wraps_and_reads_before_writing(self):
        result, output = self.run_kopt(
            b"func test()\nentry:\n  const v1, -1\n  add v1, v1, 2\n"
            b"  sub v2, 0, v1\n  mul v2, v2, v2\n  ret v2\n"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(output, b"func test()\nentry:\n  ret 1\n")

    def test_unknown_writes_and_block_boundaries_kill_facts(self):
        source = (
            b"func test(v0)\r\nentry:\r\n  const v1, 10\r\n  load v1, v0\r\n"
            b"  add v2, v1, 3\r\n  const v3, 9\r\n  jmp finish\r\n"
            b"finish:\r\n  add v4, v3, 2\r\n  div v5, v4, 0\r\n  ret v2\r\n"
        )
        result, output = self.run_kopt(source, extra_args=("--profile", "unused.prof"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(output, source.replace(b"  const v1, 10\r\n", b""))

    def test_retains_multiplication_if_const_has_higher_latency(self):
        source = b"func test()\nentry:\n  mul v0, 2, 3\n  store 0, v0\n  ret 0\n"
        result, output = self.run_kopt(source, machine=MACHINE.replace("lat_alu = 1", "lat_alu = 3"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(output, source)

    def test_signed_division_folds_toward_zero_and_wraps(self):
        result, output = self.run_kopt(
            b"func test()\nentry:\n  div v1, -2147483648, -1\n"
            b"  store 0, v1\n  div v2, -7, 2\n  store 1, v2\n"
            b"  mod v3, -7, -2\n  ret v3\n"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            output,
            b"func test()\nentry:\n  const v1, 2147483648\n  store 0, v1\n"
            b"  const v2, 4294967293\n  store 1, v2\n  ret 4294967295\n",
        )

    def test_loop_guard_proves_nonnegative_division_and_remainder(self):
        source = (
            b"func test(v0)\nentry:\n  and v0, v0, 63\n  const v1, 0\n  jmp head\n"
            b"body:\n  div v4, v1, 4\n  mod v5, v1, -8\n  store v4, v5\n"
            b"  add v1, v1, 1\n  jmp head\nhead:\n  lt v2, v1, v0\n"
            b"  br v2, body, done\ndone:\n  ret v1\n"
        )
        result, output = self.run_kopt(source)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(output, source.replace(b"div v4, v1, 4", b"shr v4, v1, 2")
                         .replace(b"mod v5, v1, -8", b"and v5, v1, 7"))

        machine = MACHINE.replace("lat_alu = 1", "lat_alu = 5")
        result, output = self.run_kopt(source, machine=machine)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(output, source)

    def test_loop_hoisting_moves_arithmetic_and_keeps_trapping_load_in_body(self):
        chain = b"  mul v2, v1, 3 ; invariant\r\n  add v3, v2, 2\r\n"
        source = (
            b"func test(v0, v1)\r\nentry:\r\n  and v0, v0, 7\r\n  jmp head\r\n"
            b"head:\r\n  br v0, body, done\r\nbody:\r\n" + chain
            + b"  load v4, v3\r\n  vstore 7, v4\r\n  sub v0, v0, 1\r\n"
            b"  jmp head\r\ndone:\r\n  ret 0\r\n"
        )
        result, output = self.run_kopt(source)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(output, source.replace(chain, b"").replace(b"  jmp head", chain + b"  jmp head", 1))

    def test_loop_hoisting_preserves_value_on_zero_iterations(self):
        source = (
            b"func test(v0, v1)\nentry:\n  const v3, 9\n  jmp head\n"
            b"head:\n  br v0, body, done\nbody:\n  mul v2, v1, 3\n  add v3, v2, 2\n"
            b"  vstore 7, v3\n  sub v0, v0, 1\n  jmp head\ndone:\n  ret v3\n"
        )
        result, output = self.run_kopt(source)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(output, source)

    def test_loop_doubling_keeps_entry_check_and_checks_each_copy(self):
        source = (
            b"func test(v0)\r\nentry:\r\n  const v1, 0\r\n  jmp head\r\n"
            b"kopt_loop_0:\r\n  ret v1\r\nhead:\r\n  lt v2, v1, v0\r\n"
            b"  br v2, body, kopt_loop_0\r\nbody:\r\n  store v1, v1\r\n"
            b"  add v1, v1, 1\r\n  jmp head ; back"
        )
        machine = MACHINE.replace("taken_branch_penalty = 0", "taken_branch_penalty = 2")
        result, output = self.run_kopt(source, machine=machine)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            output,
            source.replace(
                b"  jmp head ; back",
                b"  lt v2, v1, v0\r\n  br v2, kopt_loop_1, kopt_loop_0 ; back\r\n"
                b"kopt_loop_1:\r\n  store v1, v1\r\n  add v1, v1, 1\r\n"
                b"  lt v2, v1, v0\r\n  br v2, body, kopt_loop_0",
            ),
        )
        for variant, config in (
            (source.replace(b"store v1, v1", b"vstore v1, v1"), machine),
            (source, machine.replace("icache_size = 64", "icache_size = 9")
             .replace("icache_penalty = 0", "icache_penalty = 2")),
        ):
            with self.subTest(config=config):
                result, output = self.run_kopt(variant, machine=config)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(output, variant)

    def test_division_keeps_mixed_signs_wraparound_and_possible_zero(self):
        source = (
            b"func test(v0)\nentry:\n  br v0, negative, masked\n"
            b"negative:\n  const v1, -7\n  const v2, 0\n  jmp join\n"
            b"masked:\n  and v1, v0, 63\n  const v2, 1\n  jmp join\n"
            b"join:\n  div v3, v1, 4\n  add v4, v1, 2147483647\n"
            b"  mod v5, v4, 8\n  store 0, v3\n  div v6, v5, v2\n  ret v5\n"
        )
        result, output = self.run_kopt(source)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(output, source)

    def test_rejects_unavailable_fused_op(self):
        result, output = self.run_kopt(b"func test()\nentry:\n  mac v0, 1, 2, 3\n  ret v0\n")
        self.assertEqual(result.returncode, 1)
        self.assertIn(b"mac", result.stderr)
        self.assertIsNone(output)

    def test_copy_survives_overwrite_of_the_original_register(self):
        result, output = self.run_kopt(
            b"func test(v0)\nentry:\n  mov v1, v0\n  vload v0, 1\n"
            b"  add v2, v1, 0\n  ret v2\n"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            output,
            b"func test(v0)\nentry:\n  mov v1, v0\n  vload v0, 1\n  ret v1\n",
        )

    def test_liveness_handles_both_branch_edges_and_a_backedge(self):
        source = (
            b"func test(v0)\nentry:\n  const v1, 0\n  const v3, 7\n  jmp loop\n"
            b"loop:\n  add v1, v1, 1\n  mul v4, v0, v0\n  lt v2, v1, v0\n"
            b"  br v2, loop, done\ndone:\n  add v5, v1, v3\n  ret v5\n"
        )
        result, output = self.run_kopt(source)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(output, source.replace(b"  mul v4, v0, v0\n", b""))

    def test_dead_code_keeps_traps_and_effects(self):
        source = (
            b"func test(v0)\nentry:\n  store 0, 17\n  vload v1, 0\n"
            b"  div v2, 5, v0\n  load v3, v0\n  and v4, v0, 1\n  ret 0\n"
        )
        result, output = self.run_kopt(source)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(output, source.replace(b"  and v4, v0, 1\n", b""))

    def test_unused_load_requires_both_address_bounds(self):
        source = (
            b"func test(v0)\nentry:\n  and v1, v0, 4095\n  load v2, v1\n"
            b"  load v3, 4096\n  load v4, -1\n  ret 0\n"
        )
        result, output = self.run_kopt(source)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(output, source.replace(b"  and v1, v0, 4095\n  load v2, v1\n", b""))

    def test_negated_bounds_guard_proves_unused_load_safe(self):
        source = (
            b"func test(v0)\nentry:\n  and v1, v0, 8191\n  lt v2, v1, 4096\n"
            b"  eq v2, 0, v2\n  br v2, fault, ok\n"
            b"fault:\n  trap 7\nok:\n  load v3, v1\n  ret 0\n"
        )
        result, output = self.run_kopt(source)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(output, source.replace(b"  load v3, v1\n", b""))

    def test_overwritten_store_preserves_observers_and_trapping_continuations(self):
        prefix = (
            b"func test(v0)\nentry:\n  and v1, v0, 63\n  add v2, 100, v1\n"
            b"  store v2, 7\n"
        )
        suffix = b"  add v3, v1, 100\n  store v3, 9\n"
        for middle, ending, removed in (
            (b"", b"  ret 0\n", True),
            (b"  load v4, v2\n  vstore 7, v4\n", b"  ret 0\n", False),
            (b"  vstore 7, 0\n", b"  ret 0\n", False),
            (b"", b"  jmp fault\nfault:\n  trap 7\n", False),
        ):
            with self.subTest(middle=middle, ending=ending):
                result, output = self.run_kopt(prefix + middle + suffix + ending)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(b"  store v2, 7\n" not in output, removed)
                self.assertIn(b"  store v3, 9\n", output)

    def test_store_forwarding_keeps_the_trap_and_checks_aliases(self):
        result, output = self.run_kopt(
            b"func test(v0, v1)\nentry:\n"
            b"  store v0, 12\n  load v2, v0\n  vstore 0, v2\n"
            b"  store v1, 7\n  load v3, v0\n  ret v3\n"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            output,
            b"func test(v0, v1)\nentry:\n"
            b"  store v0, 12\n  const v2, 12\n  vstore 0, v2\n"
            b"  store v1, 7\n  load v3, v0\n  ret v3\n",
        )

    def test_constant_branch_prunes_unreachable_cycle_and_effects(self):
        for condition, targets in ((b"0", b"dead, live"), (b"-1", b"live, dead")):
            with self.subTest(condition=condition):
                source = (
                    b"func test()\r\nentry:\r\n  const v1, " + condition
                    + b"\r\n  br v1, " + targets + b"\r\ndead: ; note\r\n"
                    b"  store 0, 42\r\n  jmp cycle\r\ncycle:\r\n  jmp dead\r\n"
                    b"live:\r\n  ret 7\r\n"
                )
                result, output = self.run_kopt(source)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(output, b"func test()\r\nentry:\r\n  jmp live\r\n; note\r\nlive:\r\n  ret 7\r\n")

    def test_pruning_keeps_block_with_another_reachable_predecessor(self):
        source = (
            b"func test(v0)\nentry:\n  br v0, chooser, shared\n"
            b"chooser:\n  br 1, join, shared\nshared:\n  vstore 0, 7\n  br v0, join, join\n"
            b"join:\n  ret 0\n"
        )
        result, output = self.run_kopt(source)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            output,
            b"func test(v0)\nentry:\n  br v0, join, shared\nshared:\n  vstore 0, 7\n"
            b"  jmp join\njoin:\n  ret 0\n",
        )

    def test_jump_threading_preserves_reachable_jump_cycle(self):
        source = (
            b"func test(v0)\nentry:\n  br v0, hop, done\nhop:\n  jmp first\n"
            b"first:\n  jmp second\nsecond:\n  jmp first\ndone:\n  ret 7\n"
        )
        result, output = self.run_kopt(source)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(output, source)

    def test_jump_threading_keeps_entry_label_and_folds_equal_targets(self):
        source = (
            b"func test(v0)\nentry:\n  jmp dispatch\ndispatch:\n  br v0, left, right\n"
            b"left:\n  jmp tail\nright:\n  jmp tail\ntail:\n  ret 7\n"
        )
        result, output = self.run_kopt(source)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            output,
            b"func test(v0)\nentry:\n  jmp dispatch\ndispatch:\n  jmp tail\ntail:\n  ret 7\n",
        )

    def test_profile_moves_hot_successor_and_preserves_both_targets(self):
        source = b"; header\nfunc test(v0)\nentry:\n  br v0, hot, cold\ncold:\n  ret 0\nhot:\n  ret 7"
        profile = "edge entry hot 100\nedge entry cold 1\nedge cold hot 9999\nedge entry hot bogus\n"
        machine = MACHINE.replace("taken_branch_penalty = 0", "taken_branch_penalty = 2")
        result, output = self.run_kopt(source, machine=machine, profile=profile)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            output,
            b"; header\nfunc test(v0)\nentry:\n  br v0, hot, cold\nhot:\n  ret 7\ncold:\n  ret 0\n",
        )

    def test_zero_test_branch_inversion_preserves_profile_targets(self):
        source = (
            b"func test(v0)\nentry:\n  eq v1, 0, v0\n  br v1, zero, nonzero\n"
            b"zero:\n  ret 7\nnonzero:\n  ret v0\n"
        )
        machine = MACHINE.replace("taken_branch_penalty = 0", "taken_branch_penalty = 3")
        profile = "edge entry nonzero 100\nedge entry zero 1\n"
        result, output = self.run_kopt(source, machine=machine, profile=profile)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            output,
            b"func test(v0)\nentry:\n  br v0, nonzero, zero\n"
            b"nonzero:\n  ret v0\nzero:\n  ret 7\n",
        )

    def test_zero_test_branch_inversion_requires_current_holder(self):
        source = (
            b"func test(v0)\nentry:\n  eq v1, v0, 0\n  vload v0, 7\n"
            b"  br v1, zero, nonzero\nzero:\n  ret 7\nnonzero:\n  ret v0\n"
        )
        result, output = self.run_kopt(source)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(output, source)

        with_alias = source.replace(b"  eq v1, v0, 0", b"  mov v2, v0\n  eq v1, v0, 0")
        result, output = self.run_kopt(with_alias)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(output, with_alias.replace(b"  eq v1, v0, 0\n", b"")
                         .replace(b"br v1, zero, nonzero", b"br v2, nonzero, zero"))

    def test_layout_keeps_hot_loop_in_cache(self):
        source = b"func test(v0)\nentry:\n  br v0, done, loop\nloop:\n  jmp loop\ndone:\n  ret 7\n"
        profile = "edge entry done 10\nedge loop loop 100\n"
        machine = MACHINE.replace("taken_branch_penalty = 0", "taken_branch_penalty = 2")
        machine = machine.replace("icache_size = 64", "icache_size = 2")
        machine = machine.replace("icache_penalty = 0", "icache_penalty = 2")
        result, output = self.run_kopt(source, machine=machine, profile=profile)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(output, source)

    def test_redundant_expression_reuses_only_a_current_holder(self):
        source = (
            b"func test(v0, v1)\nentry:\n  mul v2, v0, v1\n  mul v3, v1, v0\n"
            b"  load v2, 0\n  add v4, v2, v3\n  ret v4\n"
        )
        result, output = self.run_kopt(source)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(output, source.replace(b"  mul v3, v1, v0\n", b"  mov v3, v2\n"))
        overwritten = source.replace(
            b"  mul v3, v1, v0\n  load v2, 0\n", b"  load v2, 0\n  mul v3, v1, v0\n",
        )
        result, output = self.run_kopt(overwritten)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(output, overwritten.replace(b"  mul v2, v0, v1\n", b""))

    def test_fusion_with_wrapped_shift_and_self_overwrite(self):
        source = (
            b"func test(v0, v1)\nentry:\n  shl v0, v0, 35\n"
            b"  add v0, v0, v1\n  ret v0\n"
        )
        machine = MACHINE.replace("fused_addsh = 0", "fused_addsh = 1")
        result, output = self.run_kopt(source, machine=machine)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(output, b"func test(v0, v1)\nentry:\n  addsh v0, v1, v0, 3\n  ret v0\n")
        for ineligible in (MACHINE, machine.replace("lat_addsh = 1", "lat_addsh = 3")):
            result, output = self.run_kopt(source, machine=ineligible)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(output, source)

    def test_multiply_fusion_preserves_a_live_intermediate(self):
        source = (
            b"func test(v0, v1)\nentry:\n  mul v2, v0, v1\n"
            b"  add v3, v2, v0\n  vstore 0, v2\n  ret v3\n"
        )
        machine = MACHINE.replace("fused_mac = 0", "fused_mac = 1")
        result, output = self.run_kopt(source, machine=machine)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(output, source)
        result, output = self.run_kopt(source.replace(b"  vstore 0, v2\n", b""), machine=machine)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(output, b"func test(v0, v1)\nentry:\n  mac v3, v0, v1, v0\n  ret v3\n")

    def test_power_of_two_fusion_selects_the_faster_instruction(self):
        source = (
            b"func test(v0, v1)\nentry:\n  mul v2, 0x80000000, v0\n"
            b"  add v3, v1, v2\n  ret v3\n"
        )
        machine = MACHINE.replace("fused_mac = 0", "fused_mac = 1").replace(
            "fused_addsh = 0", "fused_addsh = 1",
        )
        result, output = self.run_kopt(source, machine=machine)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(output, b"func test(v0, v1)\nentry:\n  addsh v3, v1, v0, 31\n  ret v3\n")

        result, output = self.run_kopt(source, machine=machine.replace("lat_addsh = 1", "lat_addsh = 3"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(output, b"func test(v0, v1)\nentry:\n  mac v3, 2147483648, v0, v1\n  ret v3\n")

    def test_copy_elision_checks_liveness_on_outgoing_edges(self):
        source = (
            b"func test(v0, v1, v2, v3, v4)\nentry:\n  add v5, v0, v1\n"
            b"  mov v0, v5\n  jmp next\nnext:\n  vstore v4, v0\n  ret v0\n"
        )
        machine = MACHINE.replace("reg_spill_penalty = 0", "reg_spill_penalty = 5")
        result, output = self.run_kopt(source, machine=machine)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(output, source.replace(b"add v5, v0, v1\n  mov v0, v5", b"add v0, v0, v1"))

        live_temp = source.replace(b"ret v0", b"ret v5")
        result, output = self.run_kopt(live_temp, machine=machine)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(output, live_temp)

    def test_register_reuse_preserves_join_values_and_volatile_operands(self):
        source = (
            b"func test(v0)\nentry:\n  add v1, v0, 1\n  xor v7, v1, 17\n"
            b"  br v0, hot, cold\nhot:\n  vload v10, 7\n  add v3, v10, v7\n"
            b"  load v3, v3\n  xor v4, v3, v7\n  store 4, v4\n  jmp end\n"
            b"cold:\n  add v8, v7, 2\n  mul v9, v8, 3\n  store 4, v9\n  jmp end\n"
            b"end:\n  vstore 8, v7\n  ret v7\n"
        )
        machine = MACHINE.replace("reg_spill_penalty = 0", "reg_spill_penalty = 5")
        result, output = self.run_kopt(source, machine=machine)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            output,
            b"func test(v0)\nentry:\n  add v1, v0, 1\n  xor v7, v1, 17\n"
            b"  br v0, hot, cold\nhot:\n  vload v10, 7\n  add v1, v10, v7\n"
            b"  load v1, v1\n  xor v1, v1, v7\n  store 4, v1\n  jmp end\n"
            b"cold:\n  add v1, v7, 2\n  mul v1, v1, 3\n  store 4, v1\n  jmp end\n"
            b"end:\n  vstore 8, v7\n  ret v7\n",
        )
