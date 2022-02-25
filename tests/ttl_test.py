import asyncio
import time
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


def cache_hit_test():
    t1 = time.time()
    asyncio.get_event_loop().run_until_complete(long_expiration_fn(4))
    t2 = time.time()
    asyncio.get_event_loop().run_until_complete(long_expiration_fn(4))
    t3 = time.time()
    t_first_exec = (t2 - t1) * 1000
    t_second_exec = (t3 - t2) * 1000
    print(t_first_exec)
    print(t_second_exec)
    assert t_first_exec > 4000
    assert t_second_exec < 4000


def cache_expiration_test():
    t1 = time.time()
    asyncio.get_event_loop().run_until_complete(short_expiration_fn(1))
    t2 = time.time()
    asyncio.get_event_loop().run_until_complete(short_expiration_fn(1))
    t3 = time.time()
    time.sleep(5)
    t4 = time.time()
    asyncio.get_event_loop().run_until_complete(short_expiration_fn(1))
    t5 = time.time()
    t_first_exec = (t2 - t1) * 1000
    t_second_exec = (t3 - t2) * 1000
    t_third_exec = (t5 - t4) * 1000
    print(t_first_exec)
    print(t_second_exec)
    print(t_third_exec)
    assert t_first_exec > 1000
    assert t_second_exec < 1000
    assert t_third_exec > 1000


def test_cache_refreshing_ttl():
    t1 = timeit('asyncio.get_event_loop().run_until_complete(short_cleanup_fn(1))',
                globals=globals(), number=1)
    t2 = timeit('asyncio.get_event_loop().run_until_complete(short_cleanup_fn(1))',
                globals=globals(), number=1)
    t3 = timeit('asyncio.get_event_loop().run_until_complete(short_cleanup_fn(1, use_cache=False))',
                globals=globals(), number=1)

    assert t1 > t2
    assert t1 - t3 <= 0.1


if __name__ == "__main__":
    cache_hit_test()
    cache_expiration_test()
    test_cache_refreshing_ttl()
