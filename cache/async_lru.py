from typing import Any
from collections import OrderedDict


class AsyncLRU:
    class _LRU(OrderedDict):
        def __init__(self, maxsize=128, *args, **kwargs):
            self.maxsize = maxsize
            super().__init__(*args, **kwargs)

        def __getitem__(self, key):
            value = super().__getitem__(key)
            self.move_to_end(key)
            return value

        def __setitem__(self, key, value):
            super().__setitem__(key, value)
            if len(self) > self.maxsize:
                oldest = next(iter(self))
                del self[oldest]

    class _Key:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

        def __eq__(self, obj):
            return hash(self) == hash(obj)

        def __hash__(self):
            def _hash(param: Any):
                if isinstance(param, tuple):
                    return tuple(map(_hash, param))
                if isinstance(param, dict):
                    return tuple(map(_hash, param.items()))
                elif hasattr(param, '__dict__'):
                    return str(vars(param))
                else:
                    return str(param)

            return hash(_hash(self.args) + _hash(self.kwargs))

    def __init__(self, maxsize=128):
        self.lru = self._LRU(maxsize=maxsize)

    def __call__(self, func):
        async def wrapper(*args, **kwargs):
            key = self._Key(args, kwargs)
            if key in self.lru:
                return self.lru[key]
            else:
                self.lru[key] = await func(*args, **kwargs)
                return self.lru[key]

        wrapper.__name__ += func.__name__

        return wrapper
