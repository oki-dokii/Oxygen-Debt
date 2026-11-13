import unittest

from src.forwarding import join_copies, forward, inverse_assignment, linear, literal, variable
from src.kirlib import parse_program
from src.peeling import candidates as peel


def rewritten(text):
    source = forward(parse_program(text))
    return parse_program(source) if source is not None else parse_program(text)


class ForwardingTests(unittest.TestCase):
    def test_parent_load_supplies_branch(self):
        program = rewritten('''func f(v0, v1)
entry:
  load v2, v0
  br v1, arm, done
arm:
  load v3, v0
  ret v3
done:
  ret v2
''')
        self.assertEqual(sum(ins.op == 'load' for ins in program.instrs), 1)

    def test_one_missing_join_provider_keeps_load(self):
        program = rewritten('''func f(v0, v1)
entry:
  br v1, arm, done
arm:
  load v2, v0
  jmp done
done:
  load v3, v0
  ret v3
''')
        self.assertEqual(sum(ins.op == 'load' for ins in program.instrs), 2)

    def test_aliasing_store_invalidates(self):
        program = rewritten('''func f(v0, v1)
entry:
  load v2, v0
  store v1, 9
  load v3, v0
  ret v3
''')
        self.assertEqual(sum(ins.op == 'load' for ins in program.instrs), 2)

    def test_equal_coefficients_different_offsets_are_disjoint(self):
        program = rewritten('''func f(v0)
entry:
  load v2, v0
  add v4, v0, 1
  store v4, 9
  load v3, v0
  ret v3
''')
        self.assertEqual(sum(ins.op == 'load' for ins in program.instrs), 1)

    def test_overwritten_holder_cannot_supply(self):
        program = rewritten('''func f(v0)
entry:
  load v2, v0
  const v2, 99
  load v3, v0
  ret v3
''')
        self.assertEqual(sum(ins.op == 'load' for ins in program.instrs), 2)

    def test_self_overwriting_address_does_not_cache_old_pointer(self):
        program = rewritten('''func f(v0)
entry:
  load v0, v0
  load v3, v0
  ret v3
''')
        self.assertEqual(sum(ins.op == 'load' for ins in program.instrs), 2)

    def test_odd_assignment_rebases_modular_address(self):
        program = rewritten('''func f(v0)
entry:
  mul v9, v0, 3
  add v9, v9, 7
  load v10, v9
  mac v0, v0, 3, 2
  add v11, v0, 5
  load v12, v11
  ret v12
''')
        self.assertEqual(sum(ins.op == 'load' for ins in program.instrs), 1)

    def test_even_assignment_drops_old_pointer_relation(self):
        program = rewritten('''func f(v0)
entry:
  load v2, v0
  mul v0, v0, 2
  load v3, v0
  ret v3
''')
        self.assertEqual(sum(ins.op == 'load' for ins in program.instrs), 2)

    def test_entry_backedge_does_not_invent_first_read(self):
        program = rewritten('''func f(v0)
entry:
  load v2, v0
  add v0, v0, 1
  br v2, entry, done
done:
  ret v2
''')
        self.assertEqual(sum(ins.op == 'load' for ins in program.instrs), 1)

    def test_budget_exhaustion_rejects(self):
        p = parse_program('func f(v0)\nentry:\n  load v1, v0\n  load v2, v0\n  ret v2\n')
        self.assertIsNone(forward(p, work_limit=0))

    def test_inverse_modular_coefficient_identity(self):
        for coefficient in (1, 3, 5, 17, 0x7FFFFFFF, 0xFFFFFFFF):
            source = (((0, coefficient), (1, 7)), 0xFFFFFFF9)
            inverse = inverse_assignment(source, 0)
            for old in (0, 1, 0x7FFFFFFF, 0x80000000, 0xFFFFFFFF):
                other = 0x80000009
                current = (coefficient * old + 7 * other - 7) & 0xFFFFFFFF
                values = {0: current, 1: other}
                restored = (inverse[1] + sum(c * values[r] for r, c in inverse[0])) & 0xFFFFFFFF
                self.assertEqual(restored, old)

    def test_affine_cap_drops_fact_without_truncating_terms(self):
        value = literal(0)
        for name in range(4):
            value = linear(value, variable(name))
        self.assertIsNone(linear(value, variable(4)))

    def test_peeling_rejects_multiple_entry_region(self):
        p = parse_program('''func f(v0, v1)
entry:
  br v1, head, body
head:
  br v0, body, done
body:
  load v2, v0
  sub v0, v0, 1
  jmp head
done:
  ret v0
''')
        self.assertEqual(peel(p), [])

    def test_join_names_stay_valid_when_input_uses_largest_name(self):
        program = parse_program("""func f(v999999, v17)
entry:
  br v17, left, right
left:
  load v3, v999999
  jmp done
right:
  load v4, v999999
  jmp done
done:
  load v5, v999999
  ret v5
""")
        joined = join_copies(program)
        self.assertIsNotNone(joined)
        parse_program(joined)


if __name__ == '__main__':
    unittest.main()
