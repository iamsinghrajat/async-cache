import asyncio
import time
import unittest

from cache import AsyncCache


class TestCacheFeatures(unittest.TestCase):
    def test_metrics(self):
        async def _test():
            cache = AsyncCache()
            # miss + load
            async def loader():
                return 42
            await cache.get('k1', loader=loader)
            # hit
            await cache.get('k1')
            m = cache.get_metrics()
            self.assertEqual(m['hits'], 1)
            self.assertEqual(m['misses'], 1)
            self.assertEqual(m['size'], 1)
            self.assertEqual(m['hit_rate'], 0.5)
            # clear resets? no, but size 0
            cache.clear()
            m = cache.get_metrics()
            self.assertEqual(m['size'], 0)
        asyncio.run(_test())

    def test_herd_protection(self):
        async def _test():
            cache = AsyncCache()
            calls = 0
            async def loader():
                nonlocal calls
                calls += 1
                await asyncio.sleep(0.1)
                return 'result'
            tasks = [cache.get('k', loader=loader) for _ in range(10)]
            results = await asyncio.gather(*tasks)
            self.assertEqual(len(set(results)), 1)
            self.assertEqual(calls, 1)  # herd protection: only 1 load despite 10 concurrent
            m = cache.get_metrics()
            # all 10 were cache misses (concurrent, no prior hit), but protected load
            self.assertEqual(m['misses'], 10)
            self.assertEqual(m['hits'], 0)
            self.assertEqual(m['size'], 1)
        asyncio.run(_test())

    def test_batching(self):
        async def _test():
            cache = AsyncCache(batch_window_ms=10, max_batch_size=5)
            calls = 0
            async def batch_loader(keys):
                nonlocal calls
                calls += 1
                await asyncio.sleep(0.05)
                return [f'val-{k}' for k in keys]
            tasks = [cache.get(k, batch_loader=batch_loader) for k in ['a', 'b', 'c']]
            results = await asyncio.gather(*tasks)
            self.assertEqual(results, ['val-a', 'val-b', 'val-c'])
            self.assertEqual(calls, 1)
        asyncio.run(_test())

    def test_warmup(self):
        async def _test():
            cache = AsyncCache()
            calls = 0
            async def loader1():
                nonlocal calls
                calls += 1
                return 'v1'
            async def loader2():
                nonlocal calls
                calls += 1
                return 'v2'
            await cache.warmup({'k1': loader1, 'k2': loader2})
            self.assertEqual(await cache.get('k1'), 'v1')
            self.assertEqual(await cache.get('k2'), 'v2')
            self.assertEqual(calls, 2)
        asyncio.run(_test())


if __name__ == "__main__":
    unittest.main()
