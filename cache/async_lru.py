from .key import KEY
from .lru import LRU


class AsyncLRU:
    def __init__(self, maxsize=128):
        """
        :param maxsize: Use maxsize as None for unlimited size cache
        """
        self.lru = LRU(maxsize=maxsize)
        
    def cache_clear(self):
        """
        Clears the LRU cache.

        This method empties the cache, removing all stored
        entries and effectively resetting the cache.

        :return: None
        """
        self.lru.clear()

    def __call__(self, func):
        async def wrapper(*args, use_cache=True, **kwargs):
            key = KEY(args, kwargs)
            if key in self.lru and use_cache:
                return self.lru[key]
            else:
                self.lru[key] = await func(*args, **kwargs)
                return self.lru[key]

        wrapper.__name__ += func.__name__
        wrapper.__dict__['cache_clear'] = self.cache_clear

        return wrapper
