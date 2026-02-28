"""Concurrency edge case tests for AsyncCache.

Tests for race conditions, thread safety, and concurrent access patterns.
Can be run via: python -m pytest tests/test_concurrency.py -v
Or triggered via the demo UI dashboard.
"""

import asyncio
import random
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor

from cache import AsyncCache
from cache.async_lru import AsyncLRU
from cache.async_ttl import AsyncTTL


class TestConcurrencyEdgeCases(unittest.TestCase):
    """Test concurrency-related edge cases for the async cache library."""

    def test_concurrent_metrics_accuracy(self):
        """Test that hit/miss counters are accurate under high concurrency.
        
        Without proper locking, concurrent increments can be lost,
        leading to inaccurate metrics.
        """
        async def _test():
            cache = AsyncCache(maxsize=1000)
            num_tasks = 1000
            
            # All tasks hit the same key concurrently
            async def hit_task():
                cache.set('key', 'value')
                return await cache.get('key')
            
            tasks = [hit_task() for _ in range(num_tasks)]
            await asyncio.gather(*tasks)
            
            m = cache.get_metrics()
            # All should be hits (after first set)
            self.assertEqual(m['hits'], num_tasks, 
                f"Expected {num_tasks} hits, got {m['hits']} - metrics race condition")
            self.assertEqual(m['misses'], 0)
        asyncio.run(_test())

    def test_concurrent_misses_metrics_accuracy(self):
        """Test that miss counters are accurate under concurrent misses."""
        async def _test():
            cache = AsyncCache(maxsize=1000)
            num_tasks = 500
            
            # All tasks miss on different keys concurrently
            async def miss_task(i):
                return await cache.get(f'key-{i}')
            
            tasks = [miss_task(i) for i in range(num_tasks)]
            await asyncio.gather(*tasks)
            
            m = cache.get_metrics()
            self.assertEqual(m['misses'], num_tasks,
                f"Expected {num_tasks} misses, got {m['misses']} - metrics race condition")
            self.assertEqual(m['hits'], 0)
        asyncio.run(_test())

    def test_lru_eviction_stability_under_pressure(self):
        """Test LRU eviction remains stable under high concurrent pressure.
        
        When cache size < unique keys, eviction should be deterministic
        and not cause cascading misses on re-access.
        """
        async def _test():
            maxsize = 50
            cache = AsyncCache(maxsize=maxsize)
            num_keys = 100
            
            # First pass: insert all keys concurrently
            keys = [f'key-{i}' for i in range(num_keys)]
            
            # Create proper async loader for each key
            async def value_loader():
                return 'value'
            
            tasks = [cache.get(k, loader=value_loader) for k in keys]
            await asyncio.gather(*tasks)
            
            m1 = cache.get_metrics()
            self.assertEqual(m1['size'], maxsize, 
                f"Cache should have evicted to maxsize={maxsize}, got size={m1['size']}")
            self.assertEqual(m1['misses'], num_keys)
            
            # Second pass: re-access all keys concurrently (shuffled order)
            random.shuffle(keys)
            tasks = [cache.get(k) for k in keys]
            await asyncio.gather(*tasks)
            
            m2 = cache.get_metrics()
            delta_hits = m2['hits'] - m1['hits']
            delta_misses = m2['misses'] - m1['misses']
            
            # Should have ~maxsize hits (keys still in cache)
            # and ~(num_keys - maxsize) misses (evicted keys)
            self.assertGreaterEqual(delta_hits, maxsize - 5,
                f"Expected ~{maxsize} hits on re-run, got {delta_hits}")
            self.assertLessEqual(delta_misses, num_keys - maxsize + 5,
                f"Expected ~{num_keys - maxsize} misses on re-run, got {delta_misses}")
        asyncio.run(_test())

    def test_thundering_herd_protection(self):
        """Test that thundering herd protection works correctly.
        
        When many concurrent requests miss on the same key, only one
        loader should execute.
        """
        async def _test():
            cache = AsyncCache()
            loader_calls = 0
            
            async def loader():
                nonlocal loader_calls
                loader_calls += 1
                await asyncio.sleep(0.1)  # Simulate slow load
                return 'result'
            
            # 100 concurrent requests for the same key
            tasks = [cache.get('same-key', loader=loader) for _ in range(100)]
            results = await asyncio.gather(*tasks)
            
            # All should get the same result
            self.assertEqual(len(set(results)), 1)
            self.assertEqual(results[0], 'result')
            
            # Only ONE loader should have been called
            self.assertEqual(loader_calls, 1,
                f"Expected 1 loader call (herd protection), got {loader_calls}")
            
            # All 100 should be counted as misses (they all checked cache before any loaded)
            m = cache.get_metrics()
            self.assertEqual(m['misses'], 100)
            self.assertEqual(m['size'], 1)
        asyncio.run(_test())

    def test_concurrent_set_and_get(self):
        """Test concurrent set and get operations don't cause race conditions."""
        async def _test():
            cache = AsyncCache(maxsize=1000)
            num_ops = 500
            errors = []
            
            async def set_task(i):
                try:
                    cache.set(f'key-{i % 100}', f'value-{i}')
                except Exception as e:
                    errors.append(('set', i, str(e)))
            
            async def get_task(i):
                try:
                    await cache.get(f'key-{i % 100}')
                except Exception as e:
                    errors.append(('get', i, str(e)))
            
            # Mix of concurrent sets and gets
            tasks = []
            for i in range(num_ops):
                tasks.append(set_task(i))
                tasks.append(get_task(i))
            
            await asyncio.gather(*tasks)
            
            self.assertEqual(len(errors), 0, 
                f"Concurrent operations caused errors: {errors[:5]}")
        asyncio.run(_test())

    def test_concurrent_clear_and_get(self):
        """Test that concurrent clear and get operations are safe."""
        async def _test():
            cache = AsyncCache(maxsize=100)
            
            # Pre-populate cache
            for i in range(50):
                cache.set(f'key-{i}', f'value-{i}')
            
            errors = []
            
            async def get_task(i):
                try:
                    await cache.get(f'key-{i % 50}')
                except Exception as e:
                    errors.append(('get', i, str(e)))
            
            def clear_task():
                try:
                    cache.clear()
                except Exception as e:
                    errors.append(('clear', str(e)))
            
            # Run gets and clears concurrently
            loop = asyncio.get_event_loop()
            with ThreadPoolExecutor(max_workers=10) as executor:
                # Run clears in threads (sync)
                clear_futures = [loop.run_in_executor(executor, clear_task) for _ in range(10)]
                # Run gets in async tasks
                get_tasks = [get_task(i) for i in range(500)]
                
                await asyncio.gather(*get_tasks, *clear_futures)
            
            # No crashes should occur
            self.assertEqual(len(errors), 0,
                f"Concurrent clear/get caused errors: {errors[:5]}")
        asyncio.run(_test())

    def test_decorator_concurrent_access(self):
        """Test AsyncLRU and AsyncTTL decorators under concurrent access."""
        async def _test():
            calls = {'lru': 0, 'ttl': 0}
            
            @AsyncLRU(maxsize=50)
            async def lru_func(key):
                calls['lru'] += 1
                await asyncio.sleep(0.01)
                return f'lru-{key}'
            
            @AsyncTTL(time_to_live=60, maxsize=50)
            async def ttl_func(key):
                calls['ttl'] += 1
                await asyncio.sleep(0.01)
                return f'ttl-{key}'
            
            # Concurrent calls with 100 unique keys (more than maxsize)
            keys = [f'key-{i}' for i in range(100)]
            
            lru_tasks = [lru_func(k) for k in keys]
            ttl_tasks = [ttl_func(k) for k in keys]
            
            await asyncio.gather(*lru_tasks)
            await asyncio.gather(*ttl_tasks)
            
            # Each function should have been called 100 times (all misses)
            self.assertEqual(calls['lru'], 100)
            self.assertEqual(calls['ttl'], 100)
            
            # Check metrics
            lru_metrics = lru_func.get_metrics()
            ttl_metrics = ttl_func.get_metrics()
            
            self.assertEqual(lru_metrics['size'], 50)  # Evicted to maxsize
            self.assertEqual(ttl_metrics['size'], 50)
        asyncio.run(_test())

    def test_batch_loader_concurrency(self):
        """Test batch loader under concurrent access."""
        async def _test():
            cache = AsyncCache(batch_window_ms=10, max_batch_size=50)
            batch_calls = 0
            
            async def batch_loader(keys):
                nonlocal batch_calls
                batch_calls += 1
                await asyncio.sleep(0.05)
                return [f'val-{k}' for k in keys]
            
            # Concurrent batch loads
            keys = [f'key-{i}' for i in range(100)]
            tasks = [cache.get(k, batch_loader=batch_loader) for k in keys]
            results = await asyncio.gather(*tasks)
            
            # All results should be correct
            for i, result in enumerate(results):
                self.assertEqual(result, f'val-key-{i}')
            
            # Should have batched (not 100 individual calls)
            self.assertLess(batch_calls, 100,
                f"Expected batching to reduce calls, got {batch_calls} calls")
        asyncio.run(_test())

    def test_stress_test_mixed_operations(self):
        """Stress test with mixed concurrent operations."""
        async def _test():
            cache = AsyncCache(maxsize=100)
            errors = []
            completed = {'count': 0}
            
            async def mixed_op(i):
                try:
                    op = i % 5
                    if op == 0:
                        cache.set(f'key-{i % 50}', f'value-{i}')
                    elif op == 1:
                        await cache.get(f'key-{i % 50}')
                    elif op == 2:
                        cache.delete(f'key-{i % 50}')
                    elif op == 3:
                        cache.get_metrics()
                    else:
                        async def loader():
                            return f'loaded-{i}'
                        await cache.get(f'key-{i % 50}', loader=loader)
                    completed['count'] += 1
                except Exception as e:
                    errors.append((op, i, str(e)))
            
            # 1000 mixed operations
            tasks = [mixed_op(i) for i in range(1000)]
            await asyncio.gather(*tasks)
            
            self.assertEqual(len(errors), 0,
                f"Stress test caused errors: {errors[:5]}")
            self.assertEqual(completed['count'], 1000)
        asyncio.run(_test())

    def test_metrics_consistency_after_clear(self):
        """Test that metrics are properly reset after clear under concurrency."""
        async def _test():
            cache = AsyncCache()
            
            # Generate some hits and misses
            cache.set('key', 'value')
            await cache.get('key')  # hit
            await cache.get('missing')  # miss
            
            m1 = cache.get_metrics()
            self.assertEqual(m1['hits'], 1)
            self.assertEqual(m1['misses'], 1)
            
            # Clear and verify reset
            cache.clear()
            m2 = cache.get_metrics()
            self.assertEqual(m2['hits'], 0, "Hits should be reset after clear")
            self.assertEqual(m2['misses'], 0, "Misses should be reset after clear")
            self.assertEqual(m2['size'], 0)
        asyncio.run(_test())

    def test_high_contention_same_key(self):
        """Test high contention scenario with many tasks accessing the same key."""
        async def _test():
            cache = AsyncCache()
            load_count = 0
            
            async def loader():
                nonlocal load_count
                load_count += 1
                await asyncio.sleep(0.05)  # Slow load to increase contention
                return 'shared-value'
            
            # 500 concurrent requests for the same key
            tasks = [cache.get('shared-key', loader=loader) for _ in range(500)]
            results = await asyncio.gather(*tasks)
            
            # All should get the same value
            self.assertTrue(all(r == 'shared-value' for r in results))
            
            # Only 1 load should happen (herd protection)
            self.assertEqual(load_count, 1,
                f"Expected 1 load (herd protection), got {load_count}")
            
            # All 500 should be counted as misses (concurrent check before load completes)
            m = cache.get_metrics()
            self.assertEqual(m['misses'], 500)
        asyncio.run(_test())


def run_concurrency_tests():
    """Run all concurrency tests and return results as a dict.
    
    This function can be called from the demo UI to trigger the tests.
    """
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestConcurrencyEdgeCases)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return {
        'tests_run': result.testsRun,
        'failures': len(result.failures),
        'errors': len(result.errors),
        'success': result.wasSuccessful(),
        'failure_details': [str(f) for f in result.failures],
        'error_details': [str(e) for e in result.errors]
    }


if __name__ == '__main__':
    unittest.main(verbosity=2)