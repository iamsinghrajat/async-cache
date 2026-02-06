from typing import Any


class KEY:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        kwargs.pop("use_cache", None)

    def __eq__(self, obj):
        return hash(self) == hash(obj)

    def __hash__(self):
        def _hash(param: Any):
            if isinstance(param, tuple):
                return tuple(map(_hash, param))
            if isinstance(param, dict):
                return tuple(map(_hash, param.items()))
            elif hasattr(param, "__dict__"):
                return str(vars(param))
            else:
                return str(param)

        return hash(_hash(self.args) + _hash(self.kwargs))


def make_key(func, args, kwargs, skip_args=0):
    """Reusable key: func name + sliced args + kwargs."""
    func_name = getattr(func, "__qualname__", func.__name__)
    call_args = args[skip_args:] if skip_args else args
    inner = KEY(call_args, kwargs)
    return (func_name, inner)
