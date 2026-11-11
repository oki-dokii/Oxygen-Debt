import unittest

from src.schedule import spill_contexts


class SpillContextTests(unittest.TestCase):
    def contexts(self, label, edges, sizes=None):
        predecessors = {name: [] for name in edges}
        for origin, targets in edges.items():
            for target in targets:
                predecessors[target].append(origin)
        indices = {name: list(range((sizes or {}).get(name, 2))) for name in edges}
        return spill_contexts(label, predecessors, edges, indices)

    def test_contexts_include_loop_warmup_entry_and_exit(self):
        edges = {"entry": ("head",), "head": ("body", "exit"), "body": ("head",), "exit": ()}
        paths = self.contexts("body", edges)
        self.assertIsNotNone(paths)
        self.assertTrue(any(path[0] == "entry" and path[-1] == "exit" for path in paths))
        self.assertTrue(any(path.count("body") >= 3 for path in paths))
        for path in paths:
            for before, after in zip(path, path[1:]):
                self.assertIn(after, edges[before])

    def test_branch_explosion_skips_instead_of_truncating_contexts(self):
        edges = {"entry": tuple(f"arm{i}" for i in range(9)), "body": ("exit",), "exit": ()}
        edges.update({f"arm{i}": ("body",) for i in range(9)})
        self.assertIsNone(self.contexts("body", edges))

    def test_oversized_trace_skips_optional_scheduling(self):
        edges = {"entry": ("body",), "body": ("exit",), "exit": ()}
        self.assertIsNone(self.contexts("body", edges, {"entry": 600}))


if __name__ == "__main__":
    unittest.main()
