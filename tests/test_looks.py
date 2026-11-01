# -*- coding: utf-8 -*-
"""boxbox/looks.py 的规则检查：random_look 不和已有工位撞底猫（#115），其余规则在 tests/ac/test_issue79.py。"""
import random
import unittest

from boxbox import looks


class TestRandomLookFreeCats(unittest.TestCase):
    def test_avoids_used_cats(self):
        """#115：传了已用的底猫号，随机结果一定落在还没用的号里"""
        for seed in range(200):
            rng = random.Random(seed)
            used = [rng.randint(1, looks.CAT_COUNT) for _ in range(rng.randint(0, 6))]
            lk = looks.random_look(rng, used=used)
            free = [c for c in range(1, looks.CAT_COUNT + 1) if c not in set(used)]
            if free:
                self.assertIn(lk["cat"], free, "随机到的底猫被别的工位用着：%r %r" % (used, lk["cat"]))

    def test_only_free_one_left(self):
        """已有 1–7 号猫时，新招的一定是 8 号（固定种子下任何种子都一样）"""
        used = [1, 2, 3, 4, 5, 6, 7]
        for seed in range(50):
            self.assertEqual(looks.random_look(random.Random(seed), used=used)["cat"], 8)

    def test_all_used_allows_repeat(self):
        """8 只都用过了才允许重复（还是 1..8）"""
        used = list(range(1, looks.CAT_COUNT + 1))
        for seed in range(200):
            lk = looks.random_look(random.Random(seed), used=used)
            self.assertTrue(1 <= lk["cat"] <= looks.CAT_COUNT, lk)

    def test_used_invalid_entries_ignored(self):
        """used 里的非数字（None / 字符串 / 越界号）不挡选号"""
        rng = random.Random(3)
        lk = looks.random_look(rng, used=[None, "x", 0, 99, 2])
        self.assertIn(lk["cat"], (1, 3, 4, 5, 6, 7, 8), lk)

    def test_default_unchanged(self):
        """不传 used：还是 1..8 纯随机，固定种子结果固定（#79 的老行为不变）"""
        self.assertEqual(looks.random_look(random.Random(7)), looks.random_look(random.Random(7)))
        for seed in range(50):
            self.assertTrue(1 <= looks.random_look(random.Random(seed))["cat"] <= looks.CAT_COUNT)


if __name__ == "__main__":
    unittest.main()
