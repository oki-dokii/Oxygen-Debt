import unittest
from src.kirlib import parse_program
from src.nested import hoist_nested
from src.optimizer import PURE


class NestedDominanceTests(unittest.TestCase):
    def test_definition_in_one_arm_does_not_dominate_other_arm(self):
        text=('func f(v0, v1)\nentry:\n  const v2, 0\n  jmp h\nh:\n  lt v3, v2, 1\n  br v3, body, done\n'
              'body:\n  br v0, yes, no\nyes:\n  mul v8, v1, 3\n  jmp latch\nno:\n  mov v9, v8\n  jmp latch\n'
              'latch:\n  add v2, v2, 1\n  jmp h\ndone:\n  ret v9\n')
        p=parse_program(text);starts=[p.labels[k] for k in p.block_labels]
        blocks={k:p.instrs[a:b] for k,a,b in zip(p.block_labels,starts,[*starts[1:],len(p.instrs)])}
        hoist_nested(blocks,PURE)
        self.assertTrue(any(ins.op=='mul' for ins in blocks['yes']))
        self.assertFalse(any(ins.op=='mul' for ins in blocks['entry']))
