from .async_cache import AsyncCache
from .key import make_key


class AsyncTTL:
    def __init__(self, time_to_live=60, maxsize=1024, skip_args: int = 0):
        """
        :param time_to_live: Use time_to_live as None for non expiring cache
        :param maxsize: Use maxsize as None for unlimited size cache
        :param skip_args: Use `1` to skip first arg of func in determining cache key
        """
        self.cache = AsyncCache(maxsize=maxsize, default_ttl=time_to_live)
        self.skip_args = skip_args

    def clear_cache(self):
        """
        Clears the TTL cache.

        This method empties the cache, removing all stored
        entries and effectively resetting the cache.

        :return: None
        """
        self.cache.clear()

    def __call__(self, func):
        # thin wrapper over AsyncCache; key via make_key (with skip)
        # !use_cache (force-miss/refresh): delete key then get (ensures miss count in metrics + reload)
        async def wrapper(*args, use_cache=True, **kwargs):
            key = make_key(func, args, kwargs, self.skip_args)
            if not use_cache:
                # force refresh: invalidate to trigger miss, then get+load (for correct metrics)
                self.cache.delete(key)
                # fallthrough to get below
            # get (with loader on miss; now covers force-miss case too)
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
