import asyncio
import time
import unittest
from timeit import timeit

from cache import AsyncTTL


@AsyncTTL(time_to_live=60)
async def long_expiration_fn(wait: int):
    await asyncio.sleep(wait)
    return wait


@AsyncTTL(time_to_live=5)
async def short_expiration_fn(wait: int):
    await asyncio.sleep(wait)
    return wait


@AsyncTTL(time_to_live=3)
async def short_cleanup_fn(wait: int):
    await asyncio.sleep(wait)
    return wait


@AsyncTTL(time_to_live=3)
async def cache_clear_fn(wait: int):
    await asyncio.sleep(wait)
    return wait


class TestAsyncTTL(unittest.TestCase):
    def test_hit(self):
        t1 = time.time()
        asyncio.get_event_loop().run_until_complete(long_expiration_fn(4))
        t2 = time.time()
        asyncio.get_event_loop().run_until_complete(long_expiration_fn(4))
        t3 = time.time()
        t_first = (t2 - t1) * 1000
        t_second = (t3 - t2) * 1000
        self.assertGreater(t_first, 4000)
        self.assertLess(t_second, 4000)

    def test_expiration(self):
        t1 = time.time()
        asyncio.get_event_loop().run_until_complete(short_expiration_fn(1))
        t2 = time.time()
        asyncio.get_event_loop().run_until_complete(short_expiration_fn(1))
        t3 = time.time()
        time.sleep(5)
        t4 = time.time()
        asyncio.get_event_loop().run_until_complete(short_expiration_fn(1))
        t5 = time.time()
        t_first = (t2 - t1) * 1000
        t_second = (t3 - t2) * 1000
        t_third = (t5 - t4) * 1000
        self.assertGreater(t_first, 1000)
        self.assertLess(t_second, 1000)
        self.assertGreater(t_third, 1000)

    def test_refreshing(self):
        t1 = timeit(
            "asyncio.get_event_loop().run_until_complete(short_cleanup_fn(1))",
            globals=globals(),
            number=1,
        )
        t2 = timeit(
            "asyncio.get_event_loop().run_until_complete(short_cleanup_fn(1))",
            globals=globals(),
            number=1,
        )
        t3 = timeit(
            "asyncio.get_event_loop().run_until_complete(short_cleanup_fn(1, use_cache=False))",
            globals=globals(),
            number=1,
        )
        self.assertGreater(t1, t2)
        self.assertLessEqual(t1 - t3, 0.1)

    def test_clear(self):
        t1 = time.time()
        asyncio.get_event_loop().run_until_complete(cache_clear_fn(1))
        t2 = time.time()
        asyncio.get_event_loop().run_until_complete(cache_clear_fn(1))
        t3 = time.time()
        cache_clear_fn.clear_cache()
        asyncio.get_event_loop().run_until_complete(cache_clear_fn(1))
        t4 = time.time()
        self.assertGreater(t2 - t1, 1)
        self.assertLess(t3 - t2, 1)
        self.assertGreater(t4 - t3, 1)

    def test_invalidate(self):
        # own
        t1 = time.time()
        asyncio.get_event_loop().run_until_complete(long_expiration_fn(1))
        t2 = time.time()
        asyncio.get_event_loop().run_until_complete(long_expiration_fn(1))
        t3 = time.time()
        long_expiration_fn.invalidate_cache(1)
        asyncio.get_event_loop().run_until_complete(long_expiration_fn(1))
        t4 = time.time()
        self.assertGreater(t2 - t1, 1)
        self.assertLess(t3 - t2, 1)
        self.assertGreater(t4 - t3, 1)
        # cross
        t5 = time.time()
        asyncio.get_event_loop().run_until_complete(short_expiration_fn(2))
        t6 = time.time()
        asyncio.get_event_loop().run_until_complete(short_expiration_fn(2))
        t7 = time.time()
        short_expiration_fn.invalidate_cache(2)
        asyncio.get_event_loop().run_until_complete(short_expiration_fn(2))
        t8 = time.time()
        self.assertGreater(t6 - t5, 1)
        self.assertLess(t7 - t6, 1)
        self.assertGreater(t8 - t7, 1)


if __name__ == "__main__":
    unittest.main()
