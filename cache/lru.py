from collections import OrderedDict
import threading


class LRU(OrderedDict):
    """LRU cache using OrderedDict, with Lock for concurrency safety under async tasks (prevents race in move_to_end/evict during parallel hits/sets)."""

    def __init__(self, maxsize, *args, **kwargs):
        self.maxsize = maxsize
        self._lock = threading.Lock()  # plain Lock (no re-entry needed); protects critical sections
        super().__init__(*args, **kwargs)

    def __getitem__(self, key):
        # lock hit/move_to_end to prevent interleave races in concurrent re-runs
        # deepcopy removed (not needed for immutable values; prevents potential race/slow in parallel hits)
        with self._lock:
            value = super().__getitem__(key)
            self.move_to_end(key)
            return value

    def __setitem__(self, key, value):
        # lock set+evict to ensure consistent size/eviction order in concurrent sets
        with self._lock:
            if self.maxsize is not None and self.maxsize <= 0:
                return  # maxsize=0 means no-store
            super().__setitem__(key, value)
            if self.maxsize is not None and len(self) > self.maxsize:
                oldest = next(iter(self))
                del self[oldest]

    # propagate lock to other ops if used (pop, clear, etc.)
    def pop(self, key, default=None):
        with self._lock:
            return super().pop(key, default)

    def clear(self):
        with self._lock:
            super().clear()
