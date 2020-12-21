from typing import Any
from collections import OrderedDict
import datetime


class AsyncTTL:
    class _TTL(OrderedDict):
        def __init__(self, time_to_live, min_cleanup_interval, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.time_to_live = datetime.timedelta(seconds=time_to_live)
            self.min_cleanup_interval = datetime.timedelta(seconds=min_cleanup_interval)
            self.last_expiration_cleanup_datetime = datetime.datetime.now()

        def __contains__(self, key):
            if key not in self.keys():
                return False
            else:
                key_values = super().__getitem__(key)
                key_expiration = key_values[0]
                if key_expiration < datetime.datetime.now():
                    del self[key]
                    return False
                else:
                    return True

        def __getitem__(self, key):
            value = super().__getitem__(key)
            return value

        def __setitem__(self, key, value):
            ttl_value = datetime.datetime.now() + self.time_to_live
            values = [ttl_value, value]
            super().__setitem__(key, values)

        def cleanup_expired_keys(self):
            current_datetime = datetime.datetime.now()

            if current_datetime - self.last_expiration_cleanup_datetime < self.min_cleanup_interval:
                return

            self.last_expiration_cleanup_datetime = current_datetime
            for key in list(self.keys()):
                key_expiration = self[key][0]
                if key_expiration < current_datetime:
                    del self[key]
                else:
                    break

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

    def __init__(self, time_to_live=1, min_cleanup_interval=5):
        self.ttl = self._TTL(time_to_live=time_to_live, min_cleanup_interval=min_cleanup_interval)

    def __call__(self, func):
        async def wrapper(*args, **kwargs):
            key = self._Key(args, kwargs)
            if key in self.ttl:
                val = self.ttl[key][1]
            else:
                self.ttl[key] = await func(*args, **kwargs)
                val = self.ttl[key][1]
            self.ttl.cleanup_expired_keys()
            return val

        wrapper.__name__ += func.__name__

        return wrapper
