from .key import KEY
from .lru import LRU


class AsyncLRU:

    def __init__(self, maxsize=128):
        """
        :param maxsize: Use maxsize as None for unlimited size cache
        """
        self.lru = LRU(maxsize=maxsize)

    def __call__(self, func):
        async def wrapper(*args, **kwargs):
            key = KEY(args, kwargs)
            if key in self.lru:
                return self.lru[key]
            else:
                self.lru[key] = await func(*args, **kwargs)
                return self.lru[key]

        wrapper.__name__ += func.__name__

        return wrapper
