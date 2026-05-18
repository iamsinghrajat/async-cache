# Performance Evaluation Report — Independent Verification

## Methodology

All benchmarks were written independently from scratch without referencing the planner's test suite. Configuration: 50,000 operations per run, maxsize=10,000, averaged over 3 runs per configuration. Metrics: total ops/sec, read ops/sec, write ops/sec, p50/p90/p99 latency (µs), mean lock wait time (µs).

Load profiles: 10%, 50%, 90% cache hit rate.
Concurrency levels: 10, 50, 100, 500 coroutines.

---

## Baseline (Original Code)

| Load Profile | Concurrency | Total ops/s | Read ops/s | Write ops/s | p50 µs | p90 µs | p99 µs |
|---|---|---|---|---|---|---|---|
| 10% hit | 10 | 68,802 | 6,839 | 61,963 | 1.6 | 2.1 | 4.1 |
| 10% hit | 500 | 61,957 | 6,190 | 55,767 | 1.7 | 2.2 | 3.3 |
| 50% hit | 10 | 61,938 | 30,956 | 30,982 | 1.8 | 2.6 | 3.4 |
| 50% hit | 500 | 62,713 | 31,315 | 31,398 | 1.8 | 2.6 | 3.5 |
| 90% hit | 10 | 59,766 | 53,744 | 6,022 | 2.4 | 2.8 | 4.2 |
| 90% hit | 500 | 60,320 | 54,290 | 6,030 | 2.4 | 2.7 | 3.4 |

---

## Fix 1: Replace `self.keys()` with `super().__contains__()` in `_Cache.__contains__`

**Bottleneck real?** Partially. The planner claimed `key not in self.keys()` is O(n) linear scan. This is **incorrect**: in Python 3, `dict.keys()` returns a view and `key in view` is O(1) (uses the dict's hash table). The real overhead is just the view object creation per call, which is minimal.

**My measurements (Baseline → After Fix 1):**

| Load Profile | Concurrency | Before ops/s | After ops/s | Change |
|---|---|---|---|---|
| 10% hit | 10 | 68,802 | 66,393 | -3.5% (noise) |
| 10% hit | 500 | 61,957 | 64,925 | +4.8% (noise) |
| 50% hit | 10 | 61,938 | 58,926 | -4.9% (noise) |
| 90% hit | 10 | 59,766 | 58,507 | -2.1% (noise) |
| 90% hit | 500 | 60,320 | 60,347 | +0.0% (noise) |

**Planner claimed:** +7-9% throughput improvement.
**My result:** Within noise (±5%). No consistent improvement measured.
**Match?** No. The planner's claimed O(n) bottleneck is factually incorrect for Python 3. The actual improvement from avoiding view creation is negligible.

**Verdict: ACCEPTED** — The fix is technically correct (avoids unnecessary view object allocation) and is cleaner code. The performance claim is overstated, but the change doesn't hurt.

---

## Fix 2: Replace `datetime.datetime.now()` with `time.monotonic()` for TTL

**Bottleneck real?** Yes, `datetime.datetime.now()` + `datetime.timedelta()` creates objects with syscalls, while `time.monotonic()` returns a float directly.

**My measurements (After Fix 1 → After Fix 2):**

| Load Profile | Concurrency | Before ops/s | After ops/s | Change |
|---|---|---|---|---|
| 10% hit | 10 | 66,393 | 64,777 | -2.4% (noise) |
| 50% hit | 10 | 58,926 | 56,668 | -3.8% (noise) |
| 90% hit | 50 | 58,276 | 58,573 | +0.5% (noise) |

**Planner claimed:** Marginal/within noise. Accepted for code quality.
**My result:** Within noise. Matches planner's assessment.
**Match?** Yes.

**Verdict: ACCEPTED** — Marginal performance change (within noise), accepted for code quality (simpler, no datetime dependency, monotonic clock is correct for intervals).

---

## Fix 3: Remove `threading.Lock` for hit/miss metrics counters

**Bottleneck real?** Yes. The `_metrics_lock` was acquired twice per `get()` call (once for hits, once for misses). In a single-threaded async event loop, integer increments are not preempted — the lock was pure overhead.

**My measurements (After Fix 2 → After Fix 3):**

| Load Profile | Concurrency | Before ops/s | After ops/s | Change | Before p50 | After p50 | p50 change |
|---|---|---|---|---|---|---|---|
| 10% hit | 10 | 64,777 | 67,491 | +4.2% | 1.7 | 1.7 | 0% |
| 50% hit | 10 | 56,668 | 59,384 | +4.8% | 1.9 | 1.9 | 0% |
| 90% hit | 10 | 56,964 | 58,355 | +2.4% | 2.4 | 2.2 | -8.3% |
| 90% hit | 100 | 59,862 | 62,720 | +4.8% | 2.4 | 2.1 | -12.5% |

**Planner claimed:** +8-13% throughput, p50 drop from ~6.7µs to ~3.8-5.9µs.
**My result:** +2-5% throughput, p50 at 90% hit: 2.4µs → 2.1µs (-12.5%). Direction matches, magnitude smaller (our baseline is faster so relative gains are smaller).
**Match?** Direction matches, magnitude ~2-3x smaller than claimed.

**Verdict: ACCEPTED** — Real improvement, especially in latency for read-heavy workloads. Removing unnecessary synchronization in async context is correct.

---

## Fix 4: Replace `threading.RLock` with `threading.Lock` in LRU

**Bottleneck real?** Minor. `RLock` has slight overhead for reentrant ownership tracking vs `Lock`, but in the absence of contention (single-threaded async), the difference is negligible.

**My measurements (After Fix 3 → After Fix 4):**

| Load Profile | Concurrency | Before ops/s | After ops/s | Change |
|---|---|---|---|---|
| 10% hit | 10 | 67,491 | 65,716 | -2.6% (noise) |
| 50% hit | 10 | 59,384 | 58,314 | -1.8% (noise) |
| 90% hit | 10 | 58,355 | 57,525 | -1.4% (noise) |

**Planner claimed:** Within noise (±1-2%). Accepted for correctness simplification.
**My result:** Within noise. Matches.
**Match?** Yes.

**Verdict: ACCEPTED** — No measurable improvement, accepted for correctness simplification (no re-entrant locking needed after Fix 5 changes).

---

## Fix 5: Single-call `get_if_present()` — eliminate double lookup on hot path

**Bottleneck real?** Yes. This was the **most impactful fix**. The hot path previously did:
1. `key in self.cache` → `__contains__` → `super().__getitem__()` → acquires lock
2. `self.cache[key]` → `__getitem__` → `super().__getitem__()` + `move_to_end()` → acquires lock again

Two lock acquisitions per cache hit. The new `get_if_present()` does contains + TTL check + read + `move_to_end` in one lock acquisition.

**My measurements (After Fix 4 → After Fix 5):**

| Load Profile | Concurrency | Before ops/s | After ops/s | Change | Before p50 | After p50 | p50 change |
|---|---|---|---|---|---|---|---|
| 10% hit | 10 | 65,716 | 64,677 | -1.6% (noise) | 1.6 | 1.7 | +6% (noise) |
| 50% hit | 10 | 58,314 | 60,274 | +3.4% | 1.8 | 1.6 | -11.1% |
| 50% hit | 100 | 60,955 | 59,576 | -2.3% (noise) | 1.8 | 1.6 | -11.1% |
| 90% hit | 10 | 57,525 | 59,445 | +3.3% | 2.2 | 1.3 | **-40.9%** |
| 90% hit | 50 | 58,224 | 60,383 | +3.7% | 2.2 | 1.3 | **-40.9%** |
| 90% hit | 100 | 60,149 | 62,671 | +4.2% | 2.1 | 1.3 | **-38.1%** |
| 90% hit | 500 | 56,712 | 58,407 | +3.0% | 2.2 | 1.3 | **-40.9%** |

**Planner claimed:** +6-12% throughput, p50 at 90% hit rate dropped from 3.8µs to 2.1µs (44% reduction).
**My result:** +3-4% throughput at 90% hit, p50 at 90% hit rate dropped from 2.2µs to 1.3µs (**41% reduction**). p50 reduction matches the planner's claimed percentage very closely.
**Match?** Direction and p50 reduction match closely (41% vs 44%). Throughput improvement is smaller in absolute terms but consistent.

**Verdict: ACCEPTED** — This is the single most impactful fix. The p50 latency reduction for read-heavy workloads is dramatic and matches the planner's claim.

---

## Fix 6: Reduce test sleep durations for developer productivity

**Bottleneck real?** Yes. Tests used `asyncio.sleep(4)`, `time.sleep(5)`, etc.

**My measurements:**

| Metric | Before | After | Change |
|---|---|---|---|
| Full test suite time (87 tests) | 67.85s | 7.84s | **-88.4%** |

**Planner claimed:** ~67s → ~7s (-90%).
**My result:** 67.85s → 7.84s (-88.4%).
**Match?** Yes, very close.

**Verdict: ACCEPTED** — All tests still pass with sub-second sleeps. Developer productivity improvement is significant.

---

## Overall Results (Baseline → Final with all fixes)

| Load Profile | Concurrency | Baseline ops/s | Final ops/s | Change | Baseline p50 µs | Final p50 µs | p50 Change |
|---|---|---|---|---|---|---|---|
| 10% hit | 10 | 68,802 | 65,549 | -4.7% (noise) | 1.6 | 1.8 | +12% (noise) |
| 10% hit | 500 | 61,957 | 59,648 | -3.7% (noise) | 1.7 | 1.8 | +6% (noise) |
| 50% hit | 10 | 61,938 | 58,923 | -4.9% (noise) | 1.8 | 1.7 | -5.6% |
| 50% hit | 500 | 62,713 | 58,243 | -7.1% | 1.8 | 1.7 | -5.6% |
| 90% hit | 10 | 59,766 | 60,622 | +1.4% | 2.4 | 1.3 | **-45.8%** |
| 90% hit | 50 | 60,466 | 61,707 | +2.1% | 2.5 | 1.3 | **-48.0%** |
| 90% hit | 100 | 61,652 | 62,129 | +0.8% | 2.4 | 1.3 | **-45.8%** |
| 90% hit | 500 | 60,320 | 58,360 | -3.2% (noise) | 2.4 | 1.4 | **-41.7%** |

### Key findings

- **Throughput** change is mostly within noise for our environment. The planner's claimed 18-34% throughput improvements are not reproduced. This may be due to different hardware/Python version or measurement methodology.
- **p50 latency** at 90% hit rate improved by **42-48%**, closely matching the planner's claimed 40-60%.
- **Test suite time** improved by **88%**, matching the planner's claim of ~90%.
- The most impactful fix was **Fix 5** (single-call `get_if_present()`) which eliminated redundant lock acquisition on the hot path.
- Fix 1's claimed bottleneck (O(n) scan) was factually incorrect — `dict.keys().__contains__` is O(1) in Python 3.

### Planner claim accuracy

| Fix | Claimed improvement | Measured improvement | Claim accurate? |
|---|---|---|---|
| Fix 1 | +7-9% throughput | Within noise (±5%) | No — bottleneck mischaracterized |
| Fix 2 | Within noise | Within noise | Yes |
| Fix 3 | +8-13% throughput | +2-5% throughput, -12% p50 | Partially — direction correct, magnitude overstated |
| Fix 4 | Within noise | Within noise | Yes |
| Fix 5 | +6-12% throughput, -44% p50 | +3-4% throughput, **-41% p50** | Yes — p50 matches closely |
| Fix 6 | -90% test time | **-88% test time** | Yes |
