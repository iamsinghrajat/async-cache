from .async_cache import AsyncCache
from .key import make_key


class AsyncLRU:
    def __init__(self, maxsize=128, skip_args: int = 0):
        """
        :param maxsize: Use maxsize as None for unlimited size cache
        :param skip_args: Use `1` to skip first arg of func in determining cache key (e.g., skip 'self' in methods)
        """
        self.cache = AsyncCache(maxsize=maxsize, default_ttl=None)
        self.skip_args = skip_args

    def clear_cache(self):
        """
        Clears the LRU cache.

        This method empties the cache, removing all stored
        entries and effectively resetting the cache.

        :return: None
        """
        self.cache.clear()

    def __call__(self, func):
        # thin wrapper using core AsyncCache; key via make_key (respects skip_args for parity with AsyncTTL)
        async def wrapper(*args, use_cache=True, **kwargs):
            key = make_key(func, args, kwargs, self.skip_args)
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

        # invalidate as closure (needs func + skip_args for key)
        def invalidate_cache(*args, **kwargs):
            key = make_key(func, args, kwargs, self.skip_args)
            self.cache.delete(key)
        wrapper.__dict__['invalidate_cache'] = invalidate_cache

        return wrapper
