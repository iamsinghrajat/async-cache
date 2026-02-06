from .async_cache import AsyncCache
from .key import make_key


class AsyncLRU:
    def __init__(self, maxsize=128):
        """
        :param maxsize: Use maxsize as None for unlimited size cache
        """
        self.cache = AsyncCache(maxsize=maxsize, default_ttl=None)

    def clear_cache(self):
        """
        Clears the LRU cache.

        This method empties the cache, removing all stored
        entries and effectively resetting the cache.

        :return: None
        """
        self.cache.clear()

    def __call__(self, func):
        # thin wrapper using core AsyncCache; key via make_key
        async def wrapper(*args, use_cache=True, **kwargs):
            key = make_key(func, args, kwargs)
            if not use_cache:
                # force refresh: compute + store
                val = await func(*args, **kwargs)
                self.cache.set(key, val)
                return val
            # get (with loader on miss)
            async def loader():
                return await func(*args, **kwargs)
            return await self.cache.get(key, loader=loader)

        wrapper.__name__ += func.__name__
        wrapper.__dict__['clear_cache'] = self.clear_cache
        wrapper.__dict__['get_metrics'] = self.cache.get_metrics

        # invalidate as closure (needs func for key)
        def invalidate_cache(*args, **kwargs):
            key = make_key(func, args, kwargs)
            self.cache.delete(key)
        wrapper.__dict__['invalidate_cache'] = invalidate_cache

        return wrapper
