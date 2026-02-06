import asyncio
import datetime
from collections import defaultdict

from .lru import LRU

# sentinel for set ttl param to distinguish default vs explicit None
_SENTINEL = object()


class AsyncCache:
    class _Cache(LRU):
        def __init__(self, maxsize):
            super().__init__(maxsize=maxsize)

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

        def _set(self, key, value, expiration):
            super().__setitem__(key, (value, expiration))

    def __init__(self, maxsize=128, default_ttl=None, batch_window_ms=5, max_batch_size=100):
        self.maxsize = maxsize
        self.default_ttl = default_ttl
        self.batch_window_ms = batch_window_ms
        self.max_batch_size = max_batch_size
        self.cache = self._Cache(maxsize=maxsize)
        self._pending = {}
        self._batch_pending = []
        self._batch_lock = asyncio.Lock()
        self._batch_timer = None
        self.hits = 0
        self.misses = 0

    async def get(self, key, loader=None, batch_loader=None, ttl=None):
        if key in self.cache:
            self.hits += 1
            return self.cache[key]
        # miss
        self.misses += 1
        if loader is None and batch_loader is None:
            return None
        if loader is not None:
            # single loader with herd protection
            if key in self._pending:
                return await self._pending[key]
            fut = asyncio.Future()
            self._pending[key] = fut
            try:
                value = await loader()
                ttl_arg = _SENTINEL if ttl is None else ttl
                self.set(key, value, ttl=ttl_arg)
                fut.set_result(value)
                return value
            except Exception as exc:
                fut.set_exception(exc)
                raise
            finally:
                self._pending.pop(key, None)
        # batch_loader mode
        return await self._batch_get(key, batch_loader, ttl)

    async def _batch_get(self, key, batch_loader, ttl):
        fut = asyncio.Future()
        async with self._batch_lock:
            self._batch_pending.append((key, fut, batch_loader, ttl))
            if len(self._batch_pending) >= self.max_batch_size:
                await self._flush_batch()
            elif self._batch_timer is None:
                self._batch_timer = asyncio.create_task(self._schedule_flush())
        return await fut

    async def _schedule_flush(self):
        await asyncio.sleep(self.batch_window_ms / 1000.0)
        async with self._batch_lock:
            await self._flush_batch()
            self._batch_timer = None

    async def _flush_batch(self):
        if not self._batch_pending:
            return
        # group by batch_loader (support mixed)
        groups = defaultdict(list)
        for item in self._batch_pending:
            groups[item[2]].append(item)
        self._batch_pending.clear()
        for b_loader, items in groups.items():
            keys = [it[0] for it in items]
            try:
                # assume batch_loader returns list in key order or dict
                results = await b_loader(keys)
                if isinstance(results, dict):
                    res_map = results
                else:
                    res_map = dict(zip(keys, results))
                for it in items:
                    val = res_map.get(it[0])
                    ttl_arg = _SENTINEL if it[3] is None else it[3]
                    self.set(it[0], val, ttl=ttl_arg)
                    it[1].set_result(val)
            except Exception as exc:
                for it in items:
                    it[1].set_exception(exc)

    def set(self, key, value, ttl=_SENTINEL):
        if ttl is _SENTINEL:
            use_ttl = self.default_ttl
        else:
            use_ttl = ttl
        ttl_value = (
            (datetime.datetime.now() + datetime.timedelta(seconds=use_ttl))
            if use_ttl is not None
            else None
        )
        self.cache._set(key, value, ttl_value)

    def delete(self, key):
        self.cache.pop(key, None)

    def clear(self):
        self.cache.clear()

    def get_metrics(self):
        total = self.hits + self.misses
        return {
            'hits': self.hits,
            'misses': self.misses,
            'size': len(self.cache),
            'hit_rate': (self.hits / total) if total > 0 else 0.0,
        }

    async def warmup(self, keys_with_loaders):
        for key, loader in keys_with_loaders.items():
            await self.get(key, loader=loader)
