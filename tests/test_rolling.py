import random
import unittest

from src.rolling import affine, disjoint

MASK = (1 << 32) - 1


class AffineMemoryProofTests(unittest.TestCase):
    def test_affine_operations_match_wrapping_word_arithmetic(self):
        rng = random.Random(187532)
        words = [0, 1, 31, 0x7FFFFFFF, 0x80000000, MASK, *[rng.getrandbits(32) for _ in range(20)]]
        for _ in range(200):
            a, b, constant = (rng.getrandbits(32) for _ in range(3))
            left, right, extra = (a, b), (0, constant), (2, 19)
            shift = rng.randrange(32)
            cases = [
                ("add", [left, right], lambda x, y, z: x + y),
                ("sub", [left, right], lambda x, y, z: x - y),
                ("mul", [left, right], lambda x, y, z: x * y),
                ("mac", [left, right, extra], lambda x, y, z: x * y + z),
                ("shl", [left, right], lambda x, y, z: x << (y & 31)),
                ("addsh", [left, extra, (0, shift)], lambda x, y, z: x + (y << shift)),
            ]
            for op, sources, operation in cases:
                result = affine(op, sources)
                self.assertIsNotNone(result)
                for word in words:
                    values = [(coefficient * word + offset) & MASK for coefficient, offset in sources]
                    expected = operation(*(values + [0] * (3 - len(values)))) & MASK
                    self.assertEqual((result[0] * word + result[1]) & MASK, expected)
        self.assertIsNone(affine("mul", [(1, 0), (1, 1)]))
        self.assertIsNone(affine("add", [None, (0, 1)]))

    def test_proven_disjoint_addresses_never_alias_in_the_range(self):
        rng = random.Random(85461)
        proved = 0
        for _ in range(2000):
            left, right = ((rng.choice([0, 1, 2, MASK]), rng.choice([0, 3, 17, 63, MASK])) for _ in range(2))
            low = rng.randrange(8)
            high = low + rng.randrange(16)
            if disjoint(left, right, low, high):
                proved += 1
                for word in range(low, high + 1):
                    self.assertNotEqual((left[0] * word + left[1]) & MASK,
                                        (right[0] * word + right[1]) & MASK)
        self.assertGreater(proved, 100)
        self.assertFalse(disjoint(None, (1, 0), 0, 15))
        self.assertFalse(disjoint((1, 0), (1, 0), 0, 15))


if __name__ == "__main__":
    unittest.main()
