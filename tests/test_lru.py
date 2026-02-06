import asyncio
import time
import unittest
from timeit import timeit

from cache import AsyncLRU, AsyncTTL


@AsyncLRU(maxsize=128)
async def func(wait: int):
    await asyncio.sleep(wait)


@AsyncLRU(maxsize=128)
async def cache_clear_fn(wait: int):
    await asyncio.sleep(wait)


class TestClassFunc:
    @AsyncLRU(maxsize=128)
    async def obj_func(self, wait: int):
        await asyncio.sleep(wait)

    @staticmethod
    @AsyncTTL(maxsize=128, time_to_live=None, skip_args=1)
    async def skip_arg_func(arg: int, wait: int):
        await asyncio.sleep(wait)

    @classmethod
    @AsyncLRU(maxsize=128)
    async def class_func(cls, wait: int):
        await asyncio.sleep(wait)


class TestAsyncLRU(unittest.TestCase):
    def test_basic(self):
        t1 = time.time()
        asyncio.get_event_loop().run_until_complete(func(4))
        t2 = time.time()
        asyncio.get_event_loop().run_until_complete(func(4))
        t3 = time.time()
        t_first = (t2 - t1) * 1000
        t_second = (t3 - t2) * 1000
        self.assertGreater(t_first, 4000)
        self.assertLess(t_second, 4000)

    def test_obj_method(self):
        t1 = time.time()
        obj = TestClassFunc()
        asyncio.get_event_loop().run_until_complete(obj.obj_func(4))
        t2 = time.time()
        asyncio.get_event_loop().run_until_complete(obj.obj_func(4))
        t3 = time.time()
        t_first = (t2 - t1) * 1000
        t_second = (t3 - t2) * 1000
        self.assertGreater(t_first, 4000)
        self.assertLess(t_second, 4000)

    def test_class_method(self):
        t1 = time.time()
        asyncio.get_event_loop().run_until_complete(TestClassFunc.class_func(4))
        t2 = time.time()
        asyncio.get_event_loop().run_until_complete(TestClassFunc.class_func(4))
        t3 = time.time()
        t_first = (t2 - t1) * 1000
        t_second = (t3 - t2) * 1000
        self.assertGreater(t_first, 4000)
        self.assertLess(t_second, 4000)

    def test_skip_args(self):
        t1 = time.time()
        asyncio.get_event_loop().run_until_complete(TestClassFunc.skip_arg_func(5, 4))
        t2 = time.time()
        asyncio.get_event_loop().run_until_complete(TestClassFunc.skip_arg_func(6, 4))
        t3 = time.time()
        t_first = (t2 - t1) * 1000
        t_second = (t3 - t2) * 1000
        self.assertGreater(t_first, 4000)
        self.assertLess(t_second, 4000)

    def test_refreshing(self):
        t1 = timeit(
            "asyncio.get_event_loop().run_until_complete(TestClassFunc().obj_func(1))",
            globals=globals(),
            number=1,
        )
        t2 = timeit(
            "asyncio.get_event_loop().run_until_complete(TestClassFunc().obj_func(1))",
            globals=globals(),
            number=1,
        )
        t3 = timeit(
            "asyncio.get_event_loop().run_until_complete(TestClassFunc().obj_func(1, use_cache=False))",
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
        asyncio.get_event_loop().run_until_complete(func(1))
        t2 = time.time()
        asyncio.get_event_loop().run_until_complete(func(1))
        t3 = time.time()
        func.invalidate_cache(1)
        asyncio.get_event_loop().run_until_complete(func(1))
        t4 = time.time()
        self.assertGreater(t2 - t1, 1)
        self.assertLess(t3 - t2, 1)
        self.assertGreater(t4 - t3, 1)
        # cross + skip
        obj = TestClassFunc()
        t5 = time.time()
        asyncio.get_event_loop().run_until_complete(obj.obj_func(2))
        t6 = time.time()
        asyncio.get_event_loop().run_until_complete(obj.obj_func(2))
        t7 = time.time()
        obj.obj_func.invalidate_cache(obj, 2)
        asyncio.get_event_loop().run_until_complete(obj.obj_func(2))
        t8 = time.time()
        self.assertGreater(t6 - t5, 1)
        self.assertLess(t7 - t6, 1)
        self.assertGreater(t8 - t7, 1)
        asyncio.get_event_loop().run_until_complete(TestClassFunc.skip_arg_func(100, 3))
        asyncio.get_event_loop().run_until_complete(TestClassFunc.skip_arg_func(200, 3))
        TestClassFunc.skip_arg_func.invalidate_cache(300, 3)
        t9 = time.time()
        asyncio.get_event_loop().run_until_complete(TestClassFunc.skip_arg_func(400, 3))
        t10 = time.time()
        self.assertGreater(t10 - t9, 1)


if __name__ == "__main__":
    unittest.main()
