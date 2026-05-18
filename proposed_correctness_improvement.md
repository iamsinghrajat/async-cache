# Correctness Report — async-cache

## Methodology

All issues were addressed following Test-Driven Development (TDD):
1. Identify the correctness issue in the code
2. Write a failing unit test that demonstrates the bug
3. Verify the test fails on the original code
4. Implement the minimal fix
5. Verify the test passes
6. Verify all existing tests still pass

All correctness tests are in `tests/test_correctness.py`.

---

## Issues Identified and Proposed Fixes

### Issue 1: `wrapper.__name__` concatenation bug

**Files:** `cache/async_lru.py` line 39, `cache/async_ttl.py` line 40
**Description:** Both `AsyncLRU` and `AsyncTTL` decorators set `wrapper.__name__ += func.__name__`, which produces `"wrappermy_function"` instead of `"my_function"`. This breaks introspection, logging, and any code that relies on `func.__name__` returning the original function name.
**Failing test Created:** `TestIssue1WrapperName::test_lru_wrapper_name`, `TestIssue1WrapperName::test_ttl_wrapper_name`
**Test failure message:** `AssertionError: 'wrappermy_function' != 'my_function'`
**Fix:** Changed `wrapper.__name__ += func.__name__` to `wrapper.__name__ = func.__name__` in both files.
**Status:** **FIXED** — both tests pass after fix.

---

### Issue 2: `__contains__` promotes key in LRU order (unintended side-effect)

**File:** `cache/async_cache.py` line 22
**Description:** `_Cache.__contains__` calls `super().__getitem__(key)` to check TTL expiration, which dispatches to `LRU.__getitem__`. That method calls `move_to_end(key)`, which moves the key to the most-recently-used position. This means merely *checking* if a key exists in the cache (`key in cache.cache`) has the side-effect of promoting it in the LRU eviction order. This causes wrong keys to be evicted.
**Failing test Created:** `TestIssue2ContainsPromotesLRU::test_contains_should_not_promote_key`
**Test failure message:** `AssertionError: 1 is not None : 'a' should have been evicted as LRU, but __contains__ promoted it`
**Fix:** Changed `__contains__` to use `OrderedDict.__getitem__(self, key)` directly instead of `super().__getitem__(key)`, bypassing the LRU `move_to_end` behavior. This makes containment checks read-only with respect to LRU order.
**Status:** **FIXED** — test passes after fix.

---

### Issue 3: `maxsize=0` acts as unlimited cache

**File:** `cache/lru.py` line 29
**Description:** The eviction check `if self.maxsize and len(self) > self.maxsize:` treats `0` as falsy in Python, so `maxsize=0` never triggers eviction. This means `maxsize=0` behaves identically to `maxsize=None` (unlimited cache). A user who sets `maxsize=0` logically expects no items to be stored.
**Failing test Created:** `TestIssue3MaxsizeZero::test_maxsize_zero_should_not_store`
**Test failure message:** `AssertionError: 'value' is not None : maxsize=0 should not store items, but item was found`
**Fix:** Added explicit check `if self.maxsize is not None and self.maxsize <= 0: return` at the start of `__setitem__`. Changed eviction condition to `if self.maxsize is not None and len(self) > self.maxsize:`.
**Status:** **FIXED** — test passes after fix.

---

### Issue 4: `_to_hashable` doesn't distinguish objects from different classes with same `__qualname__`

**File:** `cache/key.py` line 43
**Description:** `_to_hashable` for objects uses `type(param).__qualname__` to identify the type. If two different classes have the same `__qualname__` (e.g., same-named classes from different modules or dynamically created classes), their instances with the same attribute values produce identical hash keys. This causes cache key collisions.
**Failing test Created:** `TestIssue4ObjectModuleDistinction::test_same_named_classes_different_identity_produce_different_keys`
**Test failure message:** `AssertionError: (...'CfgA', (('x', 1),)) == (...'CfgA', (('x', 1),)) : Objects of different classes with same qualname should hash differently`
**Fix:** Added `type(param).__module__` and `id(type(param))` to the hashable tuple for objects. The tuple now includes `(module, qualname, type_id, sorted_attrs)`, making it impossible for instances of different classes to collide.
**Status:** **FIXED** — test passes after fix.

---

### Issue 5: `__contains__` deletes expired entries without holding the LRU lock

**File:** `cache/async_cache.py` line 24
**Description:** When `_Cache.__contains__` finds an expired key, it calls `del self[key]` to remove it. This `del` operation dispatches to `OrderedDict.__delitem__` without holding the LRU's `_lock`. If another thread or concurrent operation is mutating the dict simultaneously, this can cause data structure corruption. (Note: under single-threaded asyncio this is safe, but the LRU has a lock specifically for thread-safety, and this deletion bypasses it.)
**Failing test Created:** `TestIssue5ContainsDeleteWithoutLock::test_contains_expired_delete_is_safe_under_concurrent_mutation`
**Fix:** Rewrote `__contains__` to use `OrderedDict.__delitem__` inside a `with self._lock:` block, with a TOCTOU re-check. This was fixed together with Issue 2's rewrite of `__contains__`.
**Status:** **FIXED** — test passes after fix.

---

### Issue 6: Named tuples lose type distinction in `_to_hashable`

**File:** `cache/key.py` line 23
**Description:** `_to_hashable` treats all tuples uniformly (including named tuples) via `isinstance(param, (list, tuple))`. Since named tuples are subclasses of `tuple`, a `Point(1, 2)` and a plain `(1, 2)` produce the same hash key. Similarly, `Point(1, 2)` and `Pair(1, 2)` (different named tuple types with same values) produce the same hash key. This causes incorrect cache hits when different named tuple types are used as arguments.
**Failing test Created** `TestIssue7NamedTupleDistinction::test_namedtuple_vs_plain_tuple_different_keys`, `TestIssue7NamedTupleDistinction::test_different_namedtuples_same_values_different_keys`
**Test failure message:** `AssertionError: (1, 2) == (1, 2) : namedtuple and plain tuple with same values should hash differently`
**Fix:** Added a check before the generic sequence handling: `if isinstance(param, tuple) and hasattr(type(param), '_fields'):` — named tuples have a `_fields` attribute. For named tuples, the hashable includes the type's `__qualname__` to distinguish them from plain tuples and from each other.
**Status:** **FIXED** — both tests pass after fix.

---

## Summary

| Metric | Count |
|---|---|
| Total correctness issues identified | 6 |
| Issues with failing unit tests written | 6 |
| Issues successfully fixed (test passes after fix) | **6** |
| Issues not fixed | 0 |
| Total new correctness test cases | 8 |
| All existing tests still passing | Yes (95 tests) |
