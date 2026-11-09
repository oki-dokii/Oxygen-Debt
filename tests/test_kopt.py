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
    def run_kopt(self, source, machine=MACHINE, extra_args=()):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            (work / "in.kir").write_bytes(source)
            (work / "machine.cfg").write_text(machine, encoding="utf-8")
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
