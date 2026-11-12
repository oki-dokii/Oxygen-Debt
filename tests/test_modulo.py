import unittest

from src.modulo import positive_bounds
from src.ranges import UNKNOWN


class DeferredModuloBoundsTests(unittest.TestCase):
    def test_positive_wrapped_word_is_not_a_no_wrap_proof(self):
        self.assertEqual((7*700000000)&0xFFFFFFFF,605032704)
        self.assertEqual(positive_bounds('mul',[('i',7),('i',700000000)],{}),UNKNOWN)

    def test_sign_boundary_and_exact_limit(self):
        self.assertEqual(positive_bounds('add',[('i',0x7FFFFFFF),('i',1)],{}),UNKNOWN)
        self.assertEqual(positive_bounds('add',[('i',0x7FFFFFFE),('i',1)],{}),(0x7FFFFFFF,0x7FFFFFFF))
        self.assertEqual(positive_bounds('mul',[('i',65536),('i',65536)],{}),UNKNOWN)
        self.assertEqual(positive_bounds('mul',[('i',0xFFFFFFFF),('i',0xFFFFFFFF)],{}),UNKNOWN)
