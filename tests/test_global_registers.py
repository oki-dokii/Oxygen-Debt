import unittest

from src.global_registers import colour, interference, split_lifetimes
from src.kirlib import parse_program
from src.registers import register_names


def blocks(source):
    program = parse_program(source)
    starts = [program.labels[label] for label in program.block_labels]
    return program, {label: program.instrs[start:end] for label, start, end in zip(
        program.block_labels, starts, starts[1:] + [len(program.instrs)])}


class GlobalRegisterTests(unittest.TestCase):
    def test_reuses_names_across_edges(self):
        program, body = blocks('''func f(v0)
entry:
  add v10, v0, 1
  jmp middle
middle:
  store 0, v10
  add v20, v0, 2
  jmp done
done:
  ret v20
''')
        result = colour(body, program.params)
        self.assertIsNotNone(result)
        self.assertEqual(len(register_names(ins for block in result.values() for ins in block)), 2)

    def test_dead_write_interferes_with_live_through_value(self):
        program, body = blocks('''func f(v0)
entry:
  add v10, v0, 1
  const v20, 99
  ret v10
''')
        edges, _, _ = interference(body, program.params)
        self.assertIn(20, edges[10])

    def test_implicit_zeros_and_parameter_bindings(self):
        program, body = blocks('''func f(v7, v2)
entry:
  br v7, arm, done
arm:
  const v30, 5
  jmp done
done:
  add v40, v30, v31
  add v41, v40, v2
  ret v41
''')
        edges, _, _ = interference(body, program.params)
        self.assertIn(31, edges[30])
        self.assertIn(7, edges[30])
        result = colour(body, program.params)
        self.assertEqual(result['entry'][0].args[0], ('r', 7))
        self.assertEqual(result['done'][1].args[-1], ('r', 2))

    def test_dying_source_can_share_destination(self):
        program, body = blocks('''func f(v0)
entry:
  add v10, v0, 1
  add v20, v10, 3
  ret v20
''')
        edges, _, _ = interference(body, program.params)
        self.assertNotIn(20, edges[10])
        result = colour(body, program.params)
        self.assertEqual(result['entry'][1].args[0], result['entry'][1].args[1])

    def test_budget_exhaustion_rejects(self):
        program, body = blocks('''func f(v0)
entry:
  add v1, v0, 1
  jmp done
done:
  ret v1
''')
        self.assertIsNone(interference(body, program.params, budget=0))

    def test_live_loop_values_conflict(self):
        program, body = blocks('''func f(v0)
entry:
  const v10, 0
  const v20, 1
  jmp loop
loop:
  add v10, v10, v20
  add v20, v20, 1
  lt v30, v20, v0
  br v30, loop, done
done:
  ret v10
''')
        edges, _, _ = interference(body, program.params)
        self.assertIn(20, edges[10])

    def test_split_keeps_parameter_read_before_overwrite(self):
        program, body = blocks("""func f(v0)
entry:
  add v0, v0, 1
  ret v0
""")
        result = split_lifetimes(body, program.params)
        self.assertEqual(result['entry'][0].args[1], ('r', 0))
        self.assertNotEqual(result['entry'][0].args[0], ('r', 0))
        self.assertEqual(result['entry'][0].args[0], result['entry'][1].args[0])

    def test_split_unites_both_reaching_arm_definitions(self):
        program, body = blocks("""func f(v0)
entry:
  br v0, left, right
left:
  const v10, 3
  jmp done
right:
  const v10, 4
  jmp done
done:
  ret v10
""")
        result = split_lifetimes(body, program.params)
        self.assertEqual(result['left'][0].args[0], result['right'][0].args[0])
        self.assertEqual(result['done'][0].args[0], result['left'][0].args[0])

    def test_split_join_with_implicit_zero_keeps_initial_name(self):
        program, body = blocks("""func f(v0)
entry:
  br v0, left, done
left:
  const v10, 3
  jmp done
done:
  ret v10
""")
        result = split_lifetimes(body, program.params)
        self.assertEqual(result['left'][0].args[0], ('r', 10))
        self.assertEqual(result['done'][0].args[0], ('r', 10))

    def test_split_reaching_definition_budget_rejects(self):
        program, body = blocks("""func f(v0)
entry:
  add v1, v0, 1
  jmp done
done:
  ret v1
""")
        self.assertIsNone(split_lifetimes(body, program.params, budget=0))

    def test_split_unreachable_block_rejects(self):
        program, body = blocks("""func f(v0)
entry:
  ret v0
unreachable:
  ret v10
""")
        self.assertIsNone(split_lifetimes(body, program.params))


if __name__ == '__main__':
    unittest.main()
