import tempfile
import unittest
from pathlib import Path
from src.candidates import select
from src.kirlib import load_machine, parse_program
from test_kopt import MACHINE


class CandidateSelectionTests(unittest.TestCase):
    def setUp(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'machine.cfg';path.write_text(MACHINE);self.machine=load_machine(path)
        self.slow='func f(v0)\nentry:\n  const v1, 0\n  jmp h\nh:\n  lt v2, v1, 8\n  br v2, body, done\nbody:\n  add v1, v1, 1\n  jmp h\ndone:\n  ret 42\n'
        self.fast='func f(v0)\nentry:\n  ret 42\n'

    def test_rejects_incorrect_and_nonterminating_candidates(self):
        wrong=self.fast.replace('ret 42','ret 43')
        timeout='func f(v0)\nentry:\n  jmp entry\n'
        self.assertEqual(select(parse_program(self.slow),[wrong,timeout,self.fast],self.machine,{}),self.fast)

    def test_unchanged_input_remains_fallback(self):
        self.assertIsNone(select(parse_program(self.fast),[self.slow],self.machine,{}))

    def test_bad_profiles_do_not_admit_incorrect_candidates(self):
        hints={('h','body'):1,('h','done'):10**20,('missing','other'):10**30}
        for _ in range(2):
            self.assertEqual(select(parse_program(self.slow),[self.fast.replace('42','43'),self.fast],self.machine,hints),self.fast)

    def test_invalid_and_unsupported_candidates_preserve_fallback(self):
        unsupported='func f(v0)\nentry:\n  mac v1, 6, 7, 0\n  ret v1\n'
        self.assertIsNone(select(parse_program(self.slow),[unsupported],self.machine,{}))
        invalid='func f(v0)\nentry:\n  jmp missing\n'
        self.assertEqual(select(parse_program(self.slow),[invalid,self.fast],self.machine,{}),self.fast)

    def test_profile_weights_can_choose_a_different_valid_candidate(self):
        original=('func f(v0)\nentry:\n  br v0, positive, zero\npositive:\n  jmp work\nzero:\n  jmp work\nwork:\n'
                  +'  add v1, v1, 0\n'*1000+'  ret 42\n')
        fast_positive=('func f(v0)\nentry:\n  br v0, yes, no\nyes:\n  ret 42\nno:\n'
                       +'  add v1, v1, 0\n'*700+'  ret 42\n')
        fast_zero='func f(v0)\nentry:\n  br v0, yes, no\nyes:\n  const v1, 0\n  ret 42\nno:\n  ret 42\n'
        self.assertEqual(select(parse_program(original),[fast_positive,fast_zero],self.machine,{('entry','positive'):100}),fast_positive)
        self.assertEqual(select(parse_program(original),[fast_positive,fast_zero],self.machine,{('entry','zero'):100}),fast_zero)
