"""Independent correctness tests for async-cache bugs identified by planner.

Each test class corresponds to one issue from proposed_correctness_improvement.md.
Tests are written from the issue description, not copied from the planner's tests.
"""

import asyncio
import unittest

from cache import AsyncLRU, AsyncTTL, AsyncCache


class TestIssue1WrapperName(unittest.TestCase):
    """Issue 1: wrapper.__name__ += func.__name__ produces 'wrappermy_func'."""

    def test_lru_preserves_function_name(self):
        @AsyncLRU(maxsize=128)
        async def my_lru_function(x):
            return x

        self.assertEqual(my_lru_function.__name__, "my_lru_function",
                         f"Expected 'my_lru_function', got '{my_lru_function.__name__}'")

    def test_ttl_preserves_function_name(self):
        @AsyncTTL(time_to_live=60)
        async def my_ttl_function(x):
            return x

        self.assertEqual(my_ttl_function.__name__, "my_ttl_function",
                         f"Expected 'my_ttl_function', got '{my_ttl_function.__name__}'")


class TestIssue4ObjectQualnamCollision(unittest.TestCase):
    """Issue 4: _to_hashable same-qualname classes produce identical keys."""

    def test_same_named_classes_different_identity_produce_different_keys(self):
        """Two classes with same __qualname__ but different identity should hash differently."""
        from cache.key import _to_hashable

        # Dynamically create two classes with the same name
        CfgA = type('CfgA', (), {})
        CfgB = type('CfgA', (), {})  # same name, different class

        obj_a = CfgA()
        obj_a.x = 1
        obj_b = CfgB()
        obj_b.x = 1

        hash_a = _to_hashable(obj_a)
        hash_b = _to_hashable(obj_b)

        self.assertNotEqual(hash_a, hash_b,
                            "Objects of different classes with same qualname should hash differently")

    def test_same_class_same_values_same_hash(self):
        """Same class, same attribute values should produce identical hashes."""
        from cache.key import _to_hashable

        Cfg = type('Cfg', (), {})
        a = Cfg()
        a.x = 1
        b = Cfg()
        b.x = 1

        self.assertEqual(_to_hashable(a), _to_hashable(b))


class TestIssue3MaxsizeZero(unittest.TestCase):
    """Issue 3: maxsize=0 acts as unlimited cache instead of no-store."""

    def test_maxsize_zero_should_not_store(self):
        """With maxsize=0, no items should be stored in the cache."""
        async def _test():
            cache = AsyncCache(maxsize=0)
            cache.set('key', 'value')
            result = await cache.get('key')
            self.assertIsNone(result,
                              "maxsize=0 should not store items, but item was found")

        asyncio.run(_test())

    def test_maxsize_zero_cache_size_stays_zero(self):
        """Cache size should always be 0 when maxsize=0."""
        async def _test():
            cache = AsyncCache(maxsize=0)
            for i in range(10):
                cache.set(f'key{i}', f'val{i}')
            self.assertEqual(len(cache.cache), 0,
                             "Cache size should be 0 when maxsize=0")

        asyncio.run(_test())


class TestIssue6NamedTupleDistinction(unittest.TestCase):
    """Issue 6: Named tuples lose type distinction in _to_hashable."""

    def test_namedtuple_vs_plain_tuple_different_keys(self):
        """A named tuple and a plain tuple with same values should produce different keys."""
        from collections import namedtuple
        from cache.key import _to_hashable

        Point = namedtuple('Point', ['x', 'y'])
        p = Point(1, 2)
        t = (1, 2)

        self.assertNotEqual(_to_hashable(p), _to_hashable(t),
                            "namedtuple and plain tuple with same values should hash differently")

    def test_different_namedtuples_same_values_different_keys(self):
        """Two different named tuple types with same values should produce different keys."""
        from collections import namedtuple
        from cache.key import _to_hashable

        Point = namedtuple('Point', ['x', 'y'])
        Pair = namedtuple('Pair', ['x', 'y'])

        self.assertNotEqual(_to_hashable(Point(1, 2)), _to_hashable(Pair(1, 2)),
                            "Different namedtuple types with same values should hash differently")

    def test_same_namedtuple_same_values_same_key(self):
        """Same named tuple type with same values should produce same key."""
        from collections import namedtuple
        from cache.key import _to_hashable

        Point = namedtuple('Point', ['x', 'y'])
        self.assertEqual(_to_hashable(Point(1, 2)), _to_hashable(Point(1, 2)))


class TestIssue5ContainsDeleteWithoutLock(unittest.TestCase):
    """Issue 5: __contains__ deletes expired entries without holding the LRU lock."""

    def test_expired_key_deleted_safely(self):
        """Expired key deletion in __contains__ should be safe (under lock)."""
        import time
        async def _test():
            cache = AsyncCache(maxsize=10, default_ttl=0.2)
            cache.set('k1', 'v1')
            cache.set('k2', 'v2')

            time.sleep(0.3)  # let both expire

            # __contains__ should delete expired keys safely under lock
            self.assertFalse('k1' in cache.cache)
            self.assertFalse('k2' in cache.cache)
            self.assertEqual(len(cache.cache), 0)

        asyncio.run(_test())

    def test_concurrent_contains_on_expired_keys(self):
        """Multiple concurrent contains checks on expired keys should not crash."""
        import time
        async def _test():
            cache = AsyncCache(maxsize=100, default_ttl=0.1)
            for i in range(50):
                cache.set(f'k{i}', f'v{i}')

            time.sleep(0.2)

            # Concurrent contains checks on expired keys
            async def check(k):
                return k in cache.cache

            tasks = [check(f'k{i}') for i in range(50)]
            results = await asyncio.gather(*tasks)

            # All should be False (expired)
            self.assertTrue(all(not r for r in results))

        asyncio.run(_test())


class TestIssue2ContainsPromotesLRU(unittest.TestCase):
    """Issue 2: __contains__ promotes key in LRU order (side-effect)."""

    def test_contains_should_not_promote_key(self):
        """Checking 'key in cache' should not change LRU eviction order."""
        async def _test():
            cache = AsyncCache(maxsize=3)
            # Insert a, b, c — LRU order: a (oldest), b, c (newest)
            cache.set('a', 1)
            cache.set('b', 2)
            cache.set('c', 3)

            # Check if 'a' is in cache — should NOT promote 'a'
            _ = 'a' in cache.cache

            # Insert 'd' — should evict 'a' (oldest), not 'b'
            cache.set('d', 4)

            # 'a' should be evicted because it was the LRU
            result_a = await cache.get('a')
            self.assertIsNone(result_a,
                              "'a' should have been evicted as LRU, but __contains__ promoted it")
            # 'b' should still be present
            result_b = await cache.get('b')
            self.assertEqual(result_b, 2, "'b' should still be in cache")

        asyncio.run(_test())


if __name__ == "__main__":
    unittest.main()
