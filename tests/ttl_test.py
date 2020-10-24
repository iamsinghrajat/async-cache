from cache import AsyncTTL
import asyncio
import time


@AsyncTTL(time_to_live=60, min_cleanup_interval=60)
async def long_expiration_fn(wait: int):
    await asyncio.sleep(wait)


@AsyncTTL(time_to_live=5, min_cleanup_interval=60)
async def short_expiration_fn(wait: int):
    await asyncio.sleep(wait)


@AsyncTTL(time_to_live=3, min_cleanup_interval=5)
async def short_cleanup_fn(wait: int):
    await asyncio.sleep(wait)


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


def cache_cleanup_test():
    """
    Requires manual inspection into cache size after each call
    :return:
    """
    t1 = time.time()
    asyncio.get_event_loop().run_until_complete(short_cleanup_fn(1))
    t2 = time.time()
    asyncio.get_event_loop().run_until_complete(short_cleanup_fn(2))
    t3 = time.time()
    time.sleep(5)
    t4 = time.time()
    asyncio.get_event_loop().run_until_complete(short_cleanup_fn(3))
    t5 = time.time()
    t_first_exec = (t2 - t1) * 1000
    t_second_exec = (t3 - t2) * 1000
    t_third_exec = (t5 - t4) * 1000
    print(t_first_exec)
    print(t_second_exec)
    print(t_third_exec)
    assert t_first_exec > 1000
    assert t_second_exec > 2000
    assert t_third_exec > 3000


if __name__ == "__main__":
    cache_hit_test()
    cache_expiration_test()

    # Disabled test to verify auto cache cleanup for expired keys as it requires manual inspection
    # cache_cleanup_test()
