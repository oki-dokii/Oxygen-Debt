import random
import unittest
from src.bitloops import Reject, choose, constant, operate


def evaluate(vector, assignment):
    return sum((((coeff&1)^((coeff>>1)&assignment).bit_count()%2)&1)<<bit for bit,coeff in enumerate(vector))


class LinearBitProofTests(unittest.TestCase):
    def test_accepted_operations_equal_boolean_word_semantics(self):
        rng=random.Random(829171);accepted=0
        for index in range(100):
            left=tuple(rng.randrange(8) for _ in range(32))
            right=constant(rng.getrandbits(32)) if index%2 else tuple(rng.randrange(8) for _ in range(32))
            for op in ('xor','and','or','shl','shr'):
                args=[left,constant(index&31)] if op in ('shl','shr') else [left,right]
                try:result=operate(op,args)
                except Reject:continue
                accepted+=1
                for assignment in range(4):
                    a,b=(evaluate(v,assignment) for v in args)
                    expected={'xor':lambda:a^b,'and':lambda:a&b,'or':lambda:a|b,
                              'shl':lambda:(a<<(b&31))&0xFFFFFFFF,'shr':lambda:a>>(b&31)}[op]()
                    self.assertEqual(evaluate(result,assignment),expected)
        self.assertGreater(accepted,300)

    def test_linear_conditional_and_nonlinear_rejection(self):
        condition=(2,)+(0,)*31
        no=tuple(4 for _ in range(32));yes=tuple(v^((0xEDB88320>>i)&1) for i,v in enumerate(no))
        result=choose(condition,yes,no)
        for assignment in range(4):
            self.assertEqual(evaluate(result,assignment),evaluate(yes if assignment&1 else no,assignment))
        with self.assertRaises(Reject):choose(condition,(4,)+(0,)*31,constant(0))
