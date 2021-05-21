from .key import KEY
from .lru import LRU
import datetime


class AsyncTTL:
    class _TTL(LRU):
        def __init__(self, time_to_live, maxsize):
            super().__init__(maxsize=maxsize)
            self.time_to_live = datetime.timedelta(seconds=time_to_live)
            self.maxsize = maxsize

        def __contains__(self, key):
            if key not in self.keys():
                return False
            else:
                key_expiration = super().__getitem__(key)[1]
                if key_expiration < datetime.datetime.now():
                    del self[key]
                    return False
                else:
                    return True

        def __getitem__(self, key):
            value = super().__getitem__(key)[0]
            return value

        def __setitem__(self, key, value):
            ttl_value = datetime.datetime.now() + self.time_to_live
            super().__setitem__(key, (value, ttl_value))

    def __init__(self, time_to_live=60, maxsize=1024):
        """
        :param maxsize: Use maxsize as None for unlimited size cache
        """
        self.ttl = self._TTL(time_to_live=time_to_live, maxsize=maxsize)

    def __call__(self, func):
        async def wrapper(*args, **kwargs):
            key = KEY(args, kwargs)
            if key in self.ttl:
                val = self.ttl[key]
            else:
                self.ttl[key] = await func(*args, **kwargs)
                val = self.ttl[key]

            return val

        wrapper.__name__ += func.__name__

        return wrapper
