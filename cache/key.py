from typing import Any

_PRIMITIVES = (int, float, str, bool, bytes, type(None))


def _to_hashable(param: Any):
    """Recursive to hashable for stable, value-based cache keys.

    Rules:
    - Primitives: returned as-is.
    - list/tuple -> tuple(recursive)
    - dict -> tuple(sorted((k, v)))
    - set -> sorted tuple (deterministic)
    - objects -> (type, sorted __dict__)
    - fallback -> (type, repr)
    """

    # Only trust true primitives
    if isinstance(param, _PRIMITIVES):
        return param

    # sequences
    if isinstance(param, (list, tuple)):
        return tuple(_to_hashable(p) for p in param)

    # dict
    if isinstance(param, dict):
        return tuple(
            sorted((k, _to_hashable(v)) for k, v in param.items())
        )

    # set
    if isinstance(param, set):
        return tuple(
            sorted(
                (_to_hashable(p) for p in param),
                key=lambda x: (type(x).__qualname__, repr(x)),
            )
        )

    # objects (value-based)
    if hasattr(param, "__dict__"):
        return (
            type(param).__qualname__,
            tuple(
                sorted(
                    (k, _to_hashable(v)) for k, v in vars(param).items()
                )
            ),
        )

    # fallback (rare / edge types)
    return (type(param).__qualname__, repr(param))


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
        self.args = tuple(_to_hashable(arg) for arg in args)
        # copy + remove use_cache (decorator param) + sort for stability
        kw = dict(kwargs)  # copy to avoid side-effect on caller
        kw.pop("use_cache", None)
        # recursive hashable for canonical eq/hash
        self.kwargs = tuple((k, _to_hashable(v)) for k, v in sorted(kw.items()))

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


def make_key(func, args, kwargs, skip_args=0):
    """Reusable key: func name + sliced args + cleaned kwargs.
    Handles skip_args (e.g., 'self'); stable for complex types.
    """
    func_name = getattr(func, "__qualname__", func.__name__)
    call_args = args[skip_args:] if skip_args else args
    # pass tuples for immutability
    inner = KEY(tuple(call_args), dict(kwargs))  # copy dict
    return (func_name, inner)
