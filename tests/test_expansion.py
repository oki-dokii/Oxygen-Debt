import unittest

from src.expansion import cache_loads, expand
from src.kirlib import parse_program


class ExpansionSafetyTests(unittest.TestCase):
    def test_unknown_initial_parameter_cannot_choose_a_path(self):
        text = "func f(v0)\nentry:\n  br v0, entry, done\ndone:\n  ret 0\n"
        self.assertIsNone(expand(parse_program(text)))

    def test_nonparameter_initial_zero_does_not_imply_an_executed_loop(self):
        text = "func f()\nentry:\n  jmp head\ndone:\n  ret 0\nhead:\n  br v9, head, done\n"
        self.assertIsNone(expand(parse_program(text)))

    def test_nontermination_exhausts_budget(self):
        text = "func f()\nentry:\n  jmp loop\nloop:\n  jmp loop\n"
        self.assertIsNone(expand(parse_program(text)))

    def test_unknown_store_invalidates_saved_load(self):
        text = "func f(v0)\nentry:\n  load v1, 1\n  store v0, 7\n  load v2, 1\n  add v3, v1, v2\n  ret v3\n"
        self.assertIsNone(cache_loads(parse_program(text),8))

    def test_literal_store_invalidates_its_word(self):
        text = "func f()\nentry:\n  load v1, 1\n  store 1, 7\n  load v2, 1\n  add v3, v1, v2\n  ret v3\n"
        self.assertIsNone(cache_loads(parse_program(text),8))
