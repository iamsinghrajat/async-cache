from collections import OrderedDict
import copy
import threading


class LRU(OrderedDict):
    """LRU cache using OrderedDict, with RLock for concurrency safety under async tasks (prevents race in move_to_end/evict during parallel hits/sets; fixes weird hit drop near maxsize e.g. 94 vs 95)."""

    def __init__(self, maxsize, *args, **kwargs):
        self.maxsize = maxsize
        self._lock = threading.RLock()  # sync lock safe with asyncio (single loop); protects critical sections
        super().__init__(*args, **kwargs)

    def __getitem__(self, key):
        # lock hit/move_to_end to prevent interleave races in concurrent re-runs
        with self._lock:
            value = copy.deepcopy(super().__getitem__(key))
            self.move_to_end(key)
            return value

    def __setitem__(self, key, value):
        # lock set+evict to ensure consistent size/eviction order in concurrent sets
        with self._lock:
            super().__setitem__(key, value)
            if self.maxsize and len(self) > self.maxsize:
                oldest = next(iter(self))
                del self[oldest]

    # propagate lock to other ops if used (pop, clear, etc.)
    def pop(self, key, default=None):
        with self._lock:
            return super().pop(key, default)

    def clear(self):
        with self._lock:
            super().clear()
