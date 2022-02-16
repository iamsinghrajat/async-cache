import datetime
from typing import Union

from .key import KEY
from .lru import LRU


class AsyncTTL:
    class _TTL(LRU):
        def __init__(
            self, ttl: Union[datetime.timedelta, None], maxsize: Union[int, None]
        ):
            super().__init__(maxsize=maxsize)

            self.ttl = ttl if ttl else None

            self.maxsize = maxsize

        def __contains__(self, key):
            if key not in self.keys():
                return False
            else:
                key_expiration = super().__getitem__(key)[1]
                if key_expiration and key_expiration < datetime.datetime.now():
                    del self[key]
                    return False
                else:
                    return True

        def __getitem__(self, key):
            value = super().__getitem__(key)[0]
            return value

        def __setitem__(self, key, value):
            ttl_value = (datetime.datetime.now() + self.ttl) if self.ttl else None
            super().__setitem__(key, (value, ttl_value))

    def __init__(
        self,
        ttl: Union[datetime.timedelta, None] = datetime.timedelta(seconds=60),
        maxsize: Union[int, None] = 1024,
        skip_args: int = 0,
    ):
        """

        :param ttl: Use ttl as None for non expiring cache
        :param maxsize: Maximal cache size. Use None to not limit cache size.
        :param skip_args: Use `1` to skip first arg of func in determining cache key
        """
        self.ttl = self._TTL(ttl=ttl, maxsize=maxsize)
        self.skip_args = skip_args

    def __call__(self, func):
        async def wrapper(*args, **kwargs):
            key = KEY(args[self.skip_args :], kwargs)
            if key in self.ttl:
                val = self.ttl[key]
            else:
                self.ttl[key] = await func(*args, **kwargs)
                val = self.ttl[key]

            return val

        wrapper.__name__ += func.__name__

        return wrapper
