from typing import Any


def _to_hashable(param: Any):
    """Recursive to hashable for stable keys (tuples/dicts/objs).
    - Tuples recursive.
    - Dicts: sorted items tuple.
    - Objs: str(sorted vars) (deterministic).
    - Else: str (fallback).
    Fixes old unstable str(dict.items())/vars.
    """
    if isinstance(param, tuple):
        return tuple(map(_to_hashable, param))
    if isinstance(param, dict):
        return tuple(sorted((k, _to_hashable(v)) for k, v in param.items()))
    elif hasattr(param, "__dict__"):
        # stable for custom objs
        return str(sorted(vars(param).items()))
    else:
        return str(param)


class KEY:
    """Immutable, hash/eq-stable key for cache (args + kwargs).
    Fixes prior bugs:
    - __eq__ was hash-only (violated contract: a==b but hashes differ possible; collisions).
    - Hash unstable (dict.items() order pre-3.7, str(vars) arbitrary, kwargs.pop mutated caller!).
    - Now: frozen tuples, recursive _to_hashable (sorted dicts, stable obj repr), no mutation.
    Guarantees hash(a)==hash(b) iff a==b; stable across runs/Python versions.
    Used via make_key in decorators/AsyncCache.
    """

    def __init__(self, args, kwargs):
        # args: tuple; kwargs cleaned/sorted for stability
        self.args = args  # tuple for hash/eq
        # copy + remove use_cache (decorator param) + sort for stability
        kw = dict(kwargs)  # copy to avoid side-effect on caller
        kw.pop("use_cache", None)
        # recursive hashable for canonical eq/hash
        self.kwargs = tuple(_to_hashable((k, v)) for k, v in sorted(kw.items()))

    def __eq__(self, obj):
        """Value equality: must match hash contract."""
        if not isinstance(obj, KEY):
            return NotImplemented
        return self.args == obj.args and self.kwargs == obj.kwargs

    def __hash__(self):
        """Stable hash: tuple of recursive hashables (from frozen args/kwargs)."""
        # self.* already hashable tuples; ensures contract with __eq__
        return hash((self.args, self.kwargs))

    def __repr__(self):
        return f"KEY(args={self.args}, kwargs={self.kwargs})"


def _to_hashable(param: Any):
    """Recursive to hashable for stable keys (tuples/dicts/objs).
    - Tuples recursive.
    - Dicts: sorted items tuple.
    - Objs: str(vars) (deterministic repr).
    - Else: str (fallback).
    Prevents instability vs. old str/dict.items().
    """
    if isinstance(param, tuple):
        return tuple(map(_to_hashable, param))
    if isinstance(param, dict):
        return tuple(sorted((k, _to_hashable(v)) for k, v in param.items()))
    elif hasattr(param, "__dict__"):
        # stable str for custom objs (vars sorted implicit in repr)
        return str(sorted(vars(param).items()))
    else:
        return str(param)


def make_key(func, args, kwargs, skip_args=0):
    """Reusable key: func name + sliced args + cleaned kwargs.
    Handles skip_args (e.g., 'self'); stable for complex types.
    """
    func_name = getattr(func, "__qualname__", func.__name__)
    call_args = args[skip_args:] if skip_args else args
    # pass tuples for immutability
    inner = KEY(tuple(call_args), dict(kwargs))  # copy dict
    return (func_name, inner)
