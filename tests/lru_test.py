import asyncio
import time
from timeit import timeit

from cache import AsyncLRU, AsyncTTL


@AsyncLRU(maxsize=128)
async def func(wait: int):
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


def test():
    t1 = time.time()
    asyncio.get_event_loop().run_until_complete(func(4))
    t2 = time.time()
    asyncio.get_event_loop().run_until_complete(func(4))
    t3 = time.time()
    t_first_exec = (t2 - t1) * 1000
    t_second_exec = (t3 - t2) * 1000
    print(t_first_exec)
    print(t_second_exec)
    assert t_first_exec > 4000
    assert t_second_exec < 4000


def test_obj_fn():
    t1 = time.time()
    obj = TestClassFunc()
    asyncio.get_event_loop().run_until_complete(obj.obj_func(4))
    t2 = time.time()
    asyncio.get_event_loop().run_until_complete(obj.obj_func(4))
    t3 = time.time()
    t_first_exec = (t2 - t1) * 1000
    t_second_exec = (t3 - t2) * 1000
    print(t_first_exec)
    print(t_second_exec)
    assert t_first_exec > 4000
    assert t_second_exec < 4000


def test_class_fn():
    t1 = time.time()
    asyncio.get_event_loop().run_until_complete(TestClassFunc.class_func(4))
    t2 = time.time()
    asyncio.get_event_loop().run_until_complete(TestClassFunc.class_func(4))
    t3 = time.time()
    t_first_exec = (t2 - t1) * 1000
    t_second_exec = (t3 - t2) * 1000
    print(t_first_exec)
    print(t_second_exec)
    assert t_first_exec > 4000
    assert t_second_exec < 4000


def test_skip_args():
    t1 = time.time()
    asyncio.get_event_loop().run_until_complete(TestClassFunc.skip_arg_func(5, 4))
    t2 = time.time()
    asyncio.get_event_loop().run_until_complete(TestClassFunc.skip_arg_func(6, 4))
    t3 = time.time()
    t_first_exec = (t2 - t1) * 1000
    t_second_exec = (t3 - t2) * 1000
    print(t_first_exec)
    print(t_second_exec)
    assert t_first_exec > 4000
    assert t_second_exec < 4000


def test_cache_refreshing_lru():
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

    assert t1 > t2
    assert t1 - t3 <= 0.1


if __name__ == "__main__":
    test()
    test_obj_fn()
    test_class_fn()
    test_skip_args()
    test_cache_refreshing_lru()
