import asyncio
import time
import unittest

from cache import AsyncCache


class TestAsyncCache(unittest.TestCase):
    def test_get_set(self):
        async def _test():
            cache = AsyncCache(maxsize=10)
            cache.set('k1', 'v1')
            self.assertEqual(await cache.get('k1'), 'v1')
            cache.set('k1', 'v2')
            self.assertEqual(await cache.get('k1'), 'v2')
        asyncio.run(_test())

    def test_get_miss(self):
        async def _test():
            cache = AsyncCache()
            self.assertIsNone(await cache.get('missing'))
        asyncio.run(_test())

    def test_loader(self):
        async def _test():
            cache = AsyncCache()
            calls = 0
            async def loader():
                nonlocal calls
                calls += 1
                return 'loaded'
            # miss -> loader
            val = await cache.get('k', loader=loader)
            self.assertEqual(val, 'loaded')
            self.assertEqual(calls, 1)
            # hit -> no loader
            val = await cache.get('k', loader=loader)
            self.assertEqual(val, 'loaded')
            self.assertEqual(calls, 1)
        asyncio.run(_test())

    def test_delete(self):
        async def _test():
            cache = AsyncCache()
            cache.set('k', 42)
            self.assertEqual(await cache.get('k'), 42)
            cache.delete('k')
            self.assertIsNone(await cache.get('k'))
            # delete missing ok
            cache.delete('missing')
        asyncio.run(_test())

    def test_clear(self):
        async def _test():
            cache = AsyncCache()
            cache.set('k1', 1)
            cache.set('k2', 2)
            cache.clear()
            self.assertIsNone(await cache.get('k1'))
            self.assertIsNone(await cache.get('k2'))
        asyncio.run(_test())

    def test_ttl(self):
        async def _test():
            cache = AsyncCache(default_ttl=1)
            # default ttl
            cache.set('k1', 10)
            self.assertEqual(await cache.get('k1'), 10)
            time.sleep(1.1)
            self.assertIsNone(await cache.get('k1'))
            # override ttl
            cache.set('k2', 20, ttl=2)
            self.assertEqual(await cache.get('k2'), 20)
            time.sleep(1.1)
            self.assertEqual(await cache.get('k2'), 20)
            time.sleep(1.1)
            self.assertIsNone(await cache.get('k2'))
            # no ttl
            cache.set('k3', 30, ttl=None)
            self.assertEqual(await cache.get('k3'), 30)
            time.sleep(2)
            self.assertEqual(await cache.get('k3'), 30)
        asyncio.run(_test())


if __name__ == '__main__':
    unittest.main()
