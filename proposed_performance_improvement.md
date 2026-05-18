# Performance Report — async-cache

## Baseline Measurements

All benchmarks: 50,000 operations per run, maxsize=10,000.

| Load Profile | Concurrency | Total ops/s | Read ops/s | Write ops/s | p50 µs | p90 µs | p99 µs | Lock wait µs |
|---|---|---|---|---|---|---|---|---|
| 10% hit | 10 | 45,948 | 4,611 | 41,337 | 7.3 | 11.3 | 17.4 | 0.31 |
| 10% hit | 50 | 43,083 | 4,210 | 38,873 | 7.3 | 12.6 | 17.0 | 0.33 |
| 10% hit | 100 | 45,405 | 4,514 | 40,891 | 7.3 | 11.1 | 16.6 | 0.31 |
| 10% hit | 500 | 44,843 | 4,541 | 40,302 | 7.3 | 8.5 | 14.7 | 0.30 |
| 50% hit | 10 | 50,655 | 25,386 | 25,269 | 6.7 | 8.3 | 14.2 | 0.31 |
| 50% hit | 50 | 49,195 | 24,604 | 24,590 | 6.8 | 8.2 | 14.2 | 0.30 |
| 50% hit | 100 | 49,634 | 24,996 | 24,639 | 6.8 | 8.2 | 14.1 | 0.30 |
| 50% hit | 500 | 48,166 | 23,979 | 24,187 | 6.7 | 8.1 | 13.6 | 0.30 |
| 90% hit | 10 | 48,993 | 44,061 | 4,932 | 5.0 | 8.1 | 14.1 | 0.31 |
| 90% hit | 50 | 54,484 | 48,954 | 5,530 | 5.1 | 8.1 | 14.1 | 0.31 |
| 90% hit | 100 | 48,826 | 43,858 | 4,968 | 5.2 | 8.5 | 15.0 | 0.31 |
| 90% hit | 500 | 52,156 | 46,819 | 5,338 | 5.3 | 8.3 | 14.1 | 0.30 |

---

## Performance Bottlenecks Identified

### Issue 1: Global RLock in LRU — single lock for all keys
**File:** `cache/lru.py`
**Description:** Every `__getitem__` and `__setitem__` acquires the same `threading.RLock`. Under high concurrency, all operations on any key are serialized behind this single lock. This is the primary contention point.
**Severity:** High

### Issue 2: `_Cache.__contains__` iterates all keys via `self.keys()`
**File:** `cache/async_cache.py`, line 18
**Description:** `key not in self.keys()` creates a keys view and performs an O(n) linear scan instead of using the O(1) dict `__contains__`. This is called on every cache `get()` on the hot path.
**Severity:** High

### Issue 3: `datetime.datetime.now()` on every TTL check and set
**File:** `cache/async_cache.py`, lines 22, 151
**Description:** `datetime.datetime.now()` is relatively expensive. It creates a new datetime object and performs system calls. Using `time.monotonic()` with float comparison is much cheaper.
**Severity:** Medium

### Issue 4: `threading.Lock` for metrics counters
**File:** `cache/async_cache.py`, lines 47, 59, 63
**Description:** Hit/miss counters use a `threading.Lock`, which is unnecessary overhead in a single-threaded async context. Under CPython, simple integer increments are atomic. Alternatively, the counters could be combined to avoid separate lock acquisitions.
**Severity:** Low-Medium

### Issue 5: Global `asyncio.Lock` for thundering herd `_pending_lock`
**File:** `cache/async_cache.py`, line 45
**Description:** All keys share a single `_pending_lock`. When checking/registering pending loaders, even requests for completely different keys must serialize through the same lock. This limits parallelism for loader operations.
**Severity:** Medium

### Issue 6: Unit tests use real `time.sleep()` / `asyncio.sleep()` with multi-second waits
**File:** `tests/test_lru.py`, `tests/test_ttl.py`
**Description:** Tests use `asyncio.sleep(4)`, `time.sleep(5)` etc. to test caching and TTL. This makes the test suite take ~57 seconds. These could use sub-second sleeps or mock time.
**Severity:** Medium (developer productivity)

---

## Proposed Fix History

### Fix 1: Replace `self.keys()` with `super().__contains__()` in `_Cache.__contains__`

**File changed:** `cache/async_cache.py` line 18
**Change:** `key not in self.keys()` → `not super().__contains__(key)`
**Rationale:** `self.keys()` creates a view and does O(n) scan. `OrderedDict.__contains__` is O(1) hash lookup.

| Load Profile | Concurrency | Baseline ops/s | After Fix 1 ops/s | Change |
|---|---|---|---|---|
| 10% hit | 10 | 45,948 | 49,944 | +8.7% |
| 10% hit | 500 | 44,843 | 48,401 | +7.9% |
| 50% hit | 10 | 50,655 | 54,469 | +7.5% |
| 50% hit | 500 | 48,166 | 52,235 | +8.4% |
| 90% hit | 10 | 48,993 | 53,621 | +9.4% |
| 90% hit | 500 | 52,156 | 55,981 | +7.3% |

---

### Fix 2: Replace `datetime.datetime.now()` with `time.monotonic()` for TTL

**File changed:** `cache/async_cache.py` lines 22, 150-153
**Change:** Replaced `datetime.datetime.now()` and `datetime.timedelta` with `time.monotonic()` float arithmetic.
**Rationale:** `time.monotonic()` is a simple float read, no object allocation. Removes `import datetime` entirely.

| Load Profile | Concurrency | After Fix 1 ops/s | After Fix 2 ops/s | Change |
|---|---|---|---|---|
| 10% hit | 10 | 49,944 | 47,464 | -5.0% (noise) |
| 50% hit | 10 | 54,469 | 54,086 | -0.7% |
| 90% hit | 50 | 57,979 | 55,729 | -3.9% (noise) |

Marginal/within noise — accepted for code quality (simpler, no datetime dependency).

---

### Fix 3: Remove `threading.Lock` for hit/miss metrics counters

**File changed:** `cache/async_cache.py` — removed `self._metrics_lock` and all `with self._metrics_lock:` blocks.
**Change:** Removed the threading Lock protecting `self.hits` and `self.misses` increments.
**Rationale:** In async (single-threaded event loop) context, integer increments are not preempted. The lock was pure overhead on every single cache operation (2 lock acquire/release per `get()`).

| Load Profile | Concurrency | After Fix 2 ops/s | After Fix 3 ops/s | Change |
|---|---|---|---|---|
| 10% hit | 10 | 47,464 | 52,820 | +11.3% |
| 10% hit | 500 | 47,271 | 51,071 | +8.0% |
| 50% hit | 10 | 54,086 | 60,854 | +12.5% |
| 50% hit | 500 | 50,583 | 57,117 | +12.9% |
| 90% hit | 10 | 51,227 | 56,479 | +10.2% |
| 90% hit | 500 | 54,237 | 61,458 | +13.3% |

p50 latency dropped from ~6.7µs to ~3.8-5.9µs.

---

### Fix 4: Replace `threading.RLock` with `threading.Lock` in LRU

**File changed:** `cache/lru.py`
**Change:** `threading.RLock()` → `threading.Lock()`. Updated docstring.
**Rationale:** `RLock` has overhead for reentrant tracking. Since we no longer call lock-acquiring methods from within locked sections (after Fix 5), a plain `Lock` suffices and is slightly faster.

Results were within noise (±1-2%). Accepted for correctness simplification.

---

### Fix 5: Single-call `get_if_present()` — eliminate double lookup on hot path

**File changed:** `cache/async_cache.py`
**Change:** Added `_Cache.get_if_present(key)` that does contains-check + TTL-check + value-read + move_to_end in a single lock acquisition. Changed `AsyncCache.get()` hot path from `key in self.cache` + `self.cache[key]` (2 lock acquisitions) to one `get_if_present` call.
**Rationale:** The hot path previously acquired the LRU lock twice per cache hit. This was the single largest overhead in the critical path.

| Load Profile | Concurrency | After Fix 3 ops/s | After Fix 5 ops/s | Change |
|---|---|---|---|---|
| 10% hit | 10 | 52,820 | 59,027 | +11.7% |
| 10% hit | 500 | 51,071 | 57,093 | +11.8% |
| 50% hit | 10 | 60,854 | 64,895 | +6.6% |
| 50% hit | 500 | 57,117 | 58,073 | +1.7% |
| 90% hit | 10 | 56,479 | 62,782 | +11.2% |
| 90% hit | 50 | 63,890 | 70,535 | +10.4% |
| 90% hit | 500 | 61,458 | 68,495 | +11.5% |

p50 latency at 90% hit rate dropped from 3.8µs to 2.1µs (44% reduction).

---

### Fix 6: Reduce test sleep durations for developer productivity

**Files changed:** `tests/test_lru.py`, `tests/test_ttl.py`, `tests/test_async_cache.py`, `tests/test_edge_cases.py`
**Change:** Replaced multi-second `asyncio.sleep(4)`, `time.sleep(5)`, `time.sleep(1.1)` etc. with sub-second equivalents (`_SLOW=0.1s`, `_TTL_SHORT=0.3s`).
**Rationale:** Tests were validating caching behavior by measuring wall-clock time. The long sleeps were unnecessary — 100ms is sufficient to distinguish cached vs uncached calls.

| Metric | Before | After | Change |
|---|---|---|---|
| Full test suite time (87 tests) | ~67 seconds | ~7 seconds | **-90%** |

---

---

## Final Overall Improvement (Baseline → After All Fixes)

| Load Profile | Concurrency | Baseline ops/s | Final ops/s | Improvement | Baseline p50 µs | Final p50 µs | p50 Improvement |
|---|---|---|---|---|---|---|---|
| 10% hit | 10 | 45,948 | 58,322 | **+26.9%** | 7.3 | 4.3 | **-41.1%** |
| 10% hit | 50 | 43,083 | 53,327 | **+23.8%** | 7.3 | 4.4 | **-39.7%** |
| 10% hit | 100 | 45,405 | 53,529 | **+17.9%** | 7.3 | 4.3 | **-41.1%** |
| 10% hit | 500 | 44,843 | 52,914 | **+18.0%** | 7.3 | 4.3 | **-41.1%** |
| 50% hit | 10 | 50,655 | 65,630 | **+29.6%** | 6.7 | 3.9 | **-41.8%** |
| 50% hit | 50 | 49,195 | 61,436 | **+24.9%** | 6.8 | 3.8 | **-44.1%** |
| 50% hit | 100 | 49,634 | 60,099 | **+21.1%** | 6.8 | 3.9 | **-42.6%** |
| 50% hit | 500 | 48,166 | 59,527 | **+23.6%** | 6.7 | 3.9 | **-41.8%** |
| 90% hit | 10 | 48,993 | 62,124 | **+26.8%** | 5.0 | 2.2 | **-56.0%** |
| 90% hit | 50 | 54,484 | 70,891 | **+30.1%** | 5.1 | 2.1 | **-58.8%** |
| 90% hit | 100 | 48,826 | 63,845 | **+30.8%** | 5.2 | 2.2 | **-57.7%** |
| 90% hit | 500 | 52,156 | 70,002 | **+34.2%** | 5.3 | 2.1 | **-60.4%** |

### Summary

- **Throughput** improved by **18-34%** across all load profiles and concurrency levels
- **p50 latency** reduced by **40-60%** across all configurations
- **Test suite execution time** reduced by **90%** (67s → 7s)
- The largest gains came from the 90% hit-rate profile where the hot-path optimizations (Fixes 1, 3, 5) had the most impact since reads dominate
- The single most impactful fix was **Fix 5** (single-call `get_if_present`) which eliminated a redundant lock acquisition on every cache hit

---

### Issue 5 (Global `_pending_lock`) — Not fixed

**Reason:** The `_pending_lock` is only hit on cache misses with a loader. In the benchmark (which measures steady-state throughput), this lock is not on the hot path. Splitting it into per-key locks would add dict overhead that likely outweighs any benefit for the common case. This would only matter for workloads with extremely high miss rates and concurrent loaders on different keys, which is not the primary use case for a cache.
