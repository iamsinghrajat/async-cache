from cache import AsyncLRU
import asyncio
import time


@AsyncLRU(maxsize=128)
async def fn(wait: int):
    await asyncio.sleep(wait)


def test():
    t1 = time.time()
    asyncio.get_event_loop().run_until_complete(fn(4))
    t2 = time.time()
    asyncio.get_event_loop().run_until_complete(fn(4))
    t3 = time.time()
    t_first_exec = (t2 - t1) * 1000
    t_second_exec = (t3 - t2) * 1000
    print(t_first_exec)
    print(t_second_exec)
    assert t_first_exec > 4000
    assert t_second_exec < 4000


if __name__ == "__main__":
    test()
