#!/usr/bin/env python3
"""
Independent performance benchmark for async-cache library.

Measures throughput and latency across different hit-rate and concurrency profiles.
Metrics: total ops/sec, read ops/sec, write ops/sec, p50/p90/p99 latency,
         mean lock wait time per operation.
"""

import asyncio
import json
import random
import statistics
import sys
import time
import threading

from cache import AsyncCache


# ---------- Configuration ----------

NUM_OPS = 50_000
MAXSIZE = 10_000
HIT_RATES = [0.10, 0.50, 0.90]
CONCURRENCY_LEVELS = [10, 50, 100, 500]
NUM_RUNS = 3  # average over multiple runs for stability


# ---------- Monkey-patch lock to measure wait time ----------

_original_lock_acquire = threading.RLock.acquire if hasattr(threading.RLock, 'acquire') else None
_lock_wait_times = []
_lock_wait_lock = threading.Lock()


class InstrumentedRLock(threading.RLock.__class__ if isinstance(threading.RLock(), type) else type(threading.RLock())):
    """RLock that records acquisition wait time."""
    def acquire(self, blocking=True, timeout=-1):
        t0 = time.perf_counter()
        result = super().acquire(blocking, timeout)
        elapsed = time.perf_counter() - t0
        with _lock_wait_lock:
            _lock_wait_times.append(elapsed)
        return result


class InstrumentedLock:
    """Wrapper around threading.Lock that records acquisition wait time."""
    def __init__(self):
        self._lock = threading.Lock()

    def acquire(self, blocking=True, timeout=-1):
        t0 = time.perf_counter()
        result = self._lock.acquire(blocking, timeout)
        elapsed = time.perf_counter() - t0
        with _lock_wait_lock:
            _lock_wait_times.append(elapsed)
        return result

    def release(self):
        self._lock.release()

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *args):
        self.release()


def clear_lock_stats():
    global _lock_wait_times
    with _lock_wait_lock:
        _lock_wait_times = []


def get_mean_lock_wait_us():
    with _lock_wait_lock:
        if not _lock_wait_times:
            return 0.0
        return statistics.mean(_lock_wait_times) * 1_000_000  # convert to µs


# ---------- Key generation ----------

def generate_keys(num_keys):
    """Generate a pool of string keys."""
    return [f"key:{i}" for i in range(num_keys)]


def generate_workload(num_ops, hit_rate, key_pool_size=MAXSIZE):
    """
    Generate a workload of (operation, key) tuples.
    
    We pre-populate the cache with `key_pool_size` keys. Then we generate
    operations where `hit_rate` fraction target keys in the cache (reads),
    and the remainder target new keys (writes/misses).
    """
    cached_keys = [f"key:{i}" for i in range(key_pool_size)]
    miss_counter = key_pool_size
    ops = []
    for _ in range(num_ops):
        if random.random() < hit_rate:
            # This should be a cache hit (read)
            ops.append(("read", random.choice(cached_keys)))
        else:
            # This should be a cache miss (write)
            ops.append(("write", f"key:{miss_counter}"))
            miss_counter += 1
    return ops, cached_keys


# ---------- Benchmark runner ----------

async def run_benchmark(hit_rate, concurrency, num_ops=NUM_OPS, maxsize=MAXSIZE):
    """Run a single benchmark configuration and return metrics."""
    cache = AsyncCache(maxsize=maxsize, default_ttl=None)

    # Pre-populate cache
    workload, cached_keys = generate_workload(num_ops, hit_rate, key_pool_size=maxsize)
    for k in cached_keys[:maxsize]:
        cache.set(k, f"val:{k}")

    # Latency tracking per operation
    latencies = []
    read_count = 0
    write_count = 0
    read_lock = asyncio.Lock()

    semaphore = asyncio.Semaphore(concurrency)

    async def do_op(op_type, key):
        nonlocal read_count, write_count
        async with semaphore:
            t0 = time.perf_counter()
            if op_type == "read":
                await cache.get(key)
            else:
                cache.set(key, f"val:{key}")
            elapsed = time.perf_counter() - t0
            return op_type, elapsed

    clear_lock_stats()

    # Run all ops concurrently (bounded by semaphore)
    t_start = time.perf_counter()
    tasks = [do_op(op_type, key) for op_type, key in workload]
    results = await asyncio.gather(*tasks)
    t_end = time.perf_counter()

    total_time = t_end - t_start

    for op_type, elapsed in results:
        latencies.append(elapsed)
        if op_type == "read":
            read_count += 1
        else:
            write_count += 1

    # Compute metrics
    latencies_us = [l * 1_000_000 for l in latencies]
    latencies_us.sort()
    n = len(latencies_us)

    total_ops_sec = num_ops / total_time
    read_ops_sec = read_count / total_time
    write_ops_sec = write_count / total_time
    p50 = latencies_us[int(n * 0.50)]
    p90 = latencies_us[int(n * 0.90)]
    p99 = latencies_us[int(n * 0.99)]
    mean_lock_wait = get_mean_lock_wait_us()

    return {
        "hit_rate": hit_rate,
        "concurrency": concurrency,
        "total_ops_sec": round(total_ops_sec),
        "read_ops_sec": round(read_ops_sec),
        "write_ops_sec": round(write_ops_sec),
        "p50_us": round(p50, 1),
        "p90_us": round(p90, 1),
        "p99_us": round(p99, 1),
        "mean_lock_wait_us": round(mean_lock_wait, 2),
    }


async def run_all_benchmarks():
    """Run all benchmark configurations."""
    results = []
    for hit_rate in HIT_RATES:
        for concurrency in CONCURRENCY_LEVELS:
            # Average over multiple runs
            run_results = []
            for _ in range(NUM_RUNS):
                r = await run_benchmark(hit_rate, concurrency)
                run_results.append(r)

            # Average the runs
            avg = {
                "hit_rate": hit_rate,
                "concurrency": concurrency,
            }
            for metric in ["total_ops_sec", "read_ops_sec", "write_ops_sec",
                           "p50_us", "p90_us", "p99_us", "mean_lock_wait_us"]:
                vals = [r[metric] for r in run_results]
                avg[metric] = round(statistics.mean(vals), 1)

            results.append(avg)
            hr_label = f"{int(hit_rate*100)}% hit"
            print(f"  {hr_label} | conc={concurrency:>3} | "
                  f"ops/s={avg['total_ops_sec']:>8.0f} | "
                  f"read={avg['read_ops_sec']:>8.0f} | write={avg['write_ops_sec']:>8.0f} | "
                  f"p50={avg['p50_us']:>6.1f}µs | p90={avg['p90_us']:>6.1f}µs | "
                  f"p99={avg['p99_us']:>6.1f}µs | lock={avg['mean_lock_wait_us']:>5.2f}µs")

    return results


def format_results_table(results, label=""):
    """Format results as a markdown table."""
    lines = []
    if label:
        lines.append(f"### {label}")
        lines.append("")
    lines.append("| Load Profile | Concurrency | Total ops/s | Read ops/s | Write ops/s | p50 µs | p90 µs | p99 µs | Lock wait µs |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for r in results:
        hr = f"{int(r['hit_rate']*100)}% hit"
        lines.append(
            f"| {hr} | {r['concurrency']} | {r['total_ops_sec']:.0f} | "
            f"{r['read_ops_sec']:.0f} | {r['write_ops_sec']:.0f} | "
            f"{r['p50_us']:.1f} | {r['p90_us']:.1f} | {r['p99_us']:.1f} | "
            f"{r['mean_lock_wait_us']:.2f} |"
        )
    return "\n".join(lines)


if __name__ == "__main__":
    label = sys.argv[1] if len(sys.argv) > 1 else "Benchmark"
    print(f"\n=== {label} ===\n")
    results = asyncio.run(run_all_benchmarks())
    print("\n" + format_results_table(results, label))

    # Save results as JSON for comparison
    outfile = sys.argv[2] if len(sys.argv) > 2 else "bench_results.json"
    with open(outfile, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to {outfile}")
