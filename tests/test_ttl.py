import asyncio
import time
import unittest
from timeit import timeit

from cache import AsyncTTL


_SLOW = 0.1  # seconds
_TTL_SHORT = 0.3  # TTL that expires quickly

@AsyncTTL(time_to_live=60)
async def long_expiration_fn(wait):
    await asyncio.sleep(wait)
    return wait


@AsyncTTL(time_to_live=_TTL_SHORT)
async def short_expiration_fn(wait):
    await asyncio.sleep(wait)
    return wait


@AsyncTTL(time_to_live=_TTL_SHORT)
async def short_cleanup_fn(wait):
    await asyncio.sleep(wait)
    return wait


@AsyncTTL(time_to_live=_TTL_SHORT)
async def cache_clear_fn(wait):
    await asyncio.sleep(wait)
    return wait


class TestAsyncTTL(unittest.TestCase):
    def test_hit(self):
        t1 = time.time()
        asyncio.run(long_expiration_fn(_SLOW))
        t2 = time.time()
        asyncio.run(long_expiration_fn(_SLOW))
        t3 = time.time()
        t_first = t2 - t1
        t_second = t3 - t2
        self.assertGreater(t_first, _SLOW * 0.8)
        self.assertLess(t_second, _SLOW * 0.8)

    def test_expiration(self):
        t1 = time.time()
        asyncio.run(short_expiration_fn(_SLOW))
        t2 = time.time()
        asyncio.run(short_expiration_fn(_SLOW))
        t3 = time.time()
        time.sleep(_TTL_SHORT + 0.1)
        t4 = time.time()
        asyncio.run(short_expiration_fn(_SLOW))
        t5 = time.time()
        t_first = t2 - t1
        t_second = t3 - t2
        t_third = t5 - t4
        self.assertGreater(t_first, _SLOW * 0.8)
        self.assertLess(t_second, _SLOW * 0.8)
        self.assertGreater(t_third, _SLOW * 0.8)

    def test_refreshing(self):
        # Create a new event loop for timeit since asyncio.run() closes the loop
        def run_with_new_loop(coro):
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(coro)
            finally:
                loop.close()
        
        t1 = timeit(
            "run_with_new_loop(short_cleanup_fn(_SLOW))",
            globals={**globals(), 'run_with_new_loop': run_with_new_loop, '_SLOW': _SLOW},
            number=1,
        )
        t2 = timeit(
            "run_with_new_loop(short_cleanup_fn(_SLOW))",
            globals={**globals(), 'run_with_new_loop': run_with_new_loop, '_SLOW': _SLOW},
            number=1,
        )
        t3 = timeit(
            "run_with_new_loop(short_cleanup_fn(_SLOW, use_cache=False))",
            globals={**globals(), 'run_with_new_loop': run_with_new_loop, '_SLOW': _SLOW},
            number=1,
        )
        self.assertGreater(t1, t2)
        self.assertLessEqual(t1 - t3, _SLOW * 0.5)

    def test_clear(self):
        t1 = time.time()
        asyncio.run(cache_clear_fn(_SLOW))
        t2 = time.time()
        asyncio.run(cache_clear_fn(_SLOW))
        t3 = time.time()
        cache_clear_fn.clear_cache()
        asyncio.run(cache_clear_fn(_SLOW))
        t4 = time.time()
        self.assertGreater(t2 - t1, _SLOW * 0.8)
        self.assertLess(t3 - t2, _SLOW * 0.8)
        self.assertGreater(t4 - t3, _SLOW * 0.8)

    def test_invalidate(self):
        # own - use unique wait values to avoid cross-test cache hits
        _INV = _SLOW + 0.01
        t1 = time.time()
        asyncio.run(long_expiration_fn(_INV))
        t2 = time.time()
        asyncio.run(long_expiration_fn(_INV))
        t3 = time.time()
        long_expiration_fn.invalidate_cache(_INV)
        asyncio.run(long_expiration_fn(_INV))
        t4 = time.time()
        self.assertGreater(t2 - t1, _INV * 0.8)
        self.assertLess(t3 - t2, _INV * 0.8)
        self.assertGreater(t4 - t3, _INV * 0.8)
        # cross
        _W2 = _SLOW + 0.02
        t5 = time.time()
        asyncio.run(short_expiration_fn(_W2))
        t6 = time.time()
        asyncio.run(short_expiration_fn(_W2))
        t7 = time.time()
        short_expiration_fn.invalidate_cache(_W2)
        asyncio.run(short_expiration_fn(_W2))
        t8 = time.time()
        self.assertGreater(t6 - t5, _W2 * 0.8)
        self.assertLess(t7 - t6, _W2 * 0.8)
        self.assertGreater(t8 - t7, _W2 * 0.8)


if __name__ == "__main__":
    unittest.main()
