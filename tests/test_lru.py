import asyncio
import time
import unittest

from cache import AsyncLRU, AsyncTTL


_SLOW = 0.1  # seconds; enough to distinguish cached vs uncached

@AsyncLRU(maxsize=128)
async def func(wait):
    await asyncio.sleep(wait)


@AsyncLRU(maxsize=128)
async def cache_clear_fn(wait):
    await asyncio.sleep(wait)


class TestClassFunc:
    @AsyncLRU(maxsize=128)
    async def obj_func(self, wait):
        await asyncio.sleep(wait)

    @staticmethod
    @AsyncTTL(maxsize=128, time_to_live=None, skip_args=1)
    async def skip_arg_func(arg, wait):
        await asyncio.sleep(wait)

    # Test skip_args on LRU too (parity)
    @staticmethod
    @AsyncLRU(maxsize=128, skip_args=1)
    async def lru_skip_arg_func(arg, wait):
        await asyncio.sleep(wait)

    @classmethod
    @AsyncLRU(maxsize=128)
    async def class_func(cls, wait):
        await asyncio.sleep(wait)


class TestAsyncLRU(unittest.TestCase):
    def test_basic(self):
        t1 = time.time()
        asyncio.run(func(_SLOW))
        t2 = time.time()
        asyncio.run(func(_SLOW))
        t3 = time.time()
        t_first = t2 - t1
        t_second = t3 - t2
        self.assertGreater(t_first, _SLOW * 0.8)
        self.assertLess(t_second, _SLOW * 0.8)

    def test_obj_method(self):
        t1 = time.time()
        obj = TestClassFunc()
        asyncio.run(obj.obj_func(_SLOW))
        t2 = time.time()
        asyncio.run(obj.obj_func(_SLOW))
        t3 = time.time()
        t_first = t2 - t1
        t_second = t3 - t2
        self.assertGreater(t_first, _SLOW * 0.8)
        self.assertLess(t_second, _SLOW * 0.8)

    def test_class_method(self):
        t1 = time.time()
        asyncio.run(TestClassFunc.class_func(_SLOW))
        t2 = time.time()
        asyncio.run(TestClassFunc.class_func(_SLOW))
        t3 = time.time()
        t_first = t2 - t1
        t_second = t3 - t2
        self.assertGreater(t_first, _SLOW * 0.8)
        self.assertLess(t_second, _SLOW * 0.8)

    def test_skip_args(self):
        # Tests skip on TTL (legacy) + now LRU
        t1 = time.time()
        asyncio.run(TestClassFunc.skip_arg_func(5, _SLOW))
        t2 = time.time()
        asyncio.run(TestClassFunc.skip_arg_func(6, _SLOW))
        t3 = time.time()
        t_first = t2 - t1
        t_second = t3 - t2
        self.assertGreater(t_first, _SLOW * 0.8)
        self.assertLess(t_second, _SLOW * 0.8)

    def test_skip_args_lru(self):
        # Verify skip_args on @AsyncLRU: diff first arg ignored in key, so hits despite arg change
        t1 = time.time()
        asyncio.run(TestClassFunc.lru_skip_arg_func(5, _SLOW))
        t2 = time.time()
        asyncio.run(TestClassFunc.lru_skip_arg_func(6, _SLOW))  # skips arg=6, hits
        t3 = time.time()
        t_first = t2 - t1
        t_second = t3 - t2
        self.assertGreater(t_first, _SLOW * 0.8)
        self.assertLess(t_second, _SLOW * 0.8)

    def test_refreshing(self):
        """Test that use_cache=False forces a refresh (non-cached call)."""
        async def _test():
            obj = TestClassFunc()
            _R = _SLOW + 0.04  # unique value to avoid cross-test cache hits
            
            # First call - should be slow (cache miss)
            t1_start = time.time()
            await obj.obj_func(_R)
            t1_end = time.time()
            t1 = t1_end - t1_start
            
            # Second call - should be fast (cache hit)
            t2_start = time.time()
            await obj.obj_func(_R)
            t2_end = time.time()
            t2 = t2_end - t2_start
            
            # Third call with use_cache=False - should be slow (forced miss)
            t3_start = time.time()
            await obj.obj_func(_R, use_cache=False)
            t3_end = time.time()
            t3 = t3_end - t3_start
            
            return t1, t2, t3
        
        t1, t2, t3 = asyncio.run(_test())
        
        # First call should be slower than cached second call
        self.assertGreater(t1, t2, "First call should be slower than cached call")
        # Forced refresh (t3) should be similar to first call (both uncached)
        self.assertLessEqual(abs(t1 - t3), _SLOW * 2, "Uncached calls should have similar timing")

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
        # own - use unique wait value to avoid cross-test cache hits
        _INV = _SLOW + 0.01
        t1 = time.time()
        asyncio.run(func(_INV))
        t2 = time.time()
        asyncio.run(func(_INV))
        t3 = time.time()
        func.invalidate_cache(_INV)
        asyncio.run(func(_INV))
        t4 = time.time()
        self.assertGreater(t2 - t1, _INV * 0.8)
        self.assertLess(t3 - t2, _INV * 0.8)
        self.assertGreater(t4 - t3, _INV * 0.8)
        # cross + skip
        obj = TestClassFunc()
        _W2 = _SLOW + 0.02
        t5 = time.time()
        asyncio.run(obj.obj_func(_W2))
        t6 = time.time()
        asyncio.run(obj.obj_func(_W2))
        t7 = time.time()
        obj.obj_func.invalidate_cache(obj, _W2)
        asyncio.run(obj.obj_func(_W2))
        t8 = time.time()
        self.assertGreater(t6 - t5, _W2 * 0.8)
        self.assertLess(t7 - t6, _W2 * 0.8)
        self.assertGreater(t8 - t7, _W2 * 0.8)
        _W3 = _SLOW + 0.03
        asyncio.run(TestClassFunc.skip_arg_func(100, _W3))
        asyncio.run(TestClassFunc.skip_arg_func(200, _W3))
        TestClassFunc.skip_arg_func.invalidate_cache(300, _W3)
        t9 = time.time()
        asyncio.run(TestClassFunc.skip_arg_func(400, _W3))
        t10 = time.time()
        self.assertGreater(t10 - t9, _W3 * 0.8)


if __name__ == "__main__":
    unittest.main()
