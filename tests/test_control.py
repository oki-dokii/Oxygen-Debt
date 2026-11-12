import unittest

from control import diamond, guarded, pointer
from src.control import rewrite
from src.kiln import compile_program, execute
from src.kirlib import parse_program


class ControlProofSafetyTests(unittest.TestCase):
    def test_cross_arm_carried_temporary_rejects(self):
        self.assertIsNone(rewrite(parse_program(diamond(variant='cross_carry')),'diamonds'))

    def test_counter_cannot_also_be_the_translated_bound(self):
        self.assertIsNone(rewrite(parse_program(pointer(variant='same_bound')),'pointers'))

    def test_skipped_loop_counter_must_not_escape(self):
        self.assertIsNone(rewrite(parse_program(pointer(variant='live_index')),'pointers'))

    def test_trap_guard_requires_exact_unit_stride(self):
        self.assertIsNone(rewrite(parse_program(guarded(variant='stride')),'guards'))

    def test_header_predicate_is_restored_before_trap_effects(self):
        original=guarded(variant='live_condition')
        transformed=rewrite(parse_program(original),'guards')
        self.assertIsNotNone(transformed)
        before=execute(compile_program(parse_program(original)),[70,0],[],{},100000)
        after=execute(compile_program(parse_program(transformed)),[70,0],[],{},100000)
        self.assertEqual(before.value,'explicit(1)')
        self.assertEqual((after.status,after.value,after.mem,after.vlog),
                         (before.status,before.value,before.mem,before.vlog))
