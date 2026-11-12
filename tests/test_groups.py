import unittest

from groups import source
from src.groups import group
from src.kiln import compile_program, execute
from src.kirlib import parse_program


class CountedGroupSafetyTests(unittest.TestCase):
    def test_unsupported_factors_reject(self):
        for factor in (0,1,3,16):self.assertIsNone(group(parse_program(source()),factor))
        self.assertIsNone(group(parse_program(source()),4,'unknown'))

    def test_possible_signed_overshoot_rejects(self):
        self.assertIsNone(group(parse_program(source(2,variant='overflow')),4))

    def test_nonpositive_stride_rejects(self):
        for stride in (0,-1):self.assertIsNone(group(parse_program(source(stride)),4))

    def test_each_body_observes_the_original_true_predicate(self):
        text=source(variant='volatile');candidate=group(parse_program(text),4,require_minimum=False)
        self.assertIsNotNone(candidate)
        before=execute(compile_program(parse_program(text)),[25,1],[],{7:[0,1,0xFFFFFFFF]},100000)
        after=execute(compile_program(parse_program(candidate)),[25,1],[],{7:[0,1,0xFFFFFFFF]},100000)
        self.assertEqual((after.status,after.value,after.mem,after.vlog),(before.status,before.value,before.mem,before.vlog))
        self.assertTrue(all(value==1 for kind,port,value in after.vlog if kind=='S' and port==9))

    def test_zero_and_short_tails_preserve_live_values(self):
        text=source(variant='predicate_update');candidate=group(parse_program(text),8,require_minimum=False)
        self.assertIsNotNone(candidate)
        for n in range(17):
            original=compile_program(parse_program(text));changed=compile_program(parse_program(candidate))
            before=execute(original,[n,7],[],{},100000,want_trace=True)
            after=execute(changed,[n,7],[],{},100000,want_trace=True)
            self.assertEqual((after.status,after.value,after.mem,after.vlog),(before.status,before.value,before.mem,before.vlog))
            if n==0:self.assertEqual([original.opnames[pc] for pc in before.trace],
                                     [changed.opnames[pc] for pc in after.trace])

    def test_production_requires_a_guaranteed_whole_group(self):
        self.assertIsNone(group(parse_program(source()),4))
        self.assertIsNotNone(group(parse_program(source(minimum=128)),8))
