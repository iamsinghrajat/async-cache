"""Comprehensive edge case tests for AsyncCache.

Tests for backward compatibility, robustness, and all features including:
- Direct cache usage (not just decorators)
- Thundering herd protection
- Batch loader / DataLoader pattern
- Cache warmup
- TTL handling edge cases
- LRU eviction edge cases
- Metrics accuracy
- Error handling
"""

import asyncio
import random
import time
import unittest
from unittest.mock import AsyncMock, patch

from cache import AsyncCache, AsyncLRU, AsyncTTL


class TestBackwardCompatibility(unittest.TestCase):
    """Ensure existing decorator-based usage still works."""
    
    def test_lru_decorator_basic(self):
        """Basic LRU decorator functionality."""
        call_count = 0
        
        @AsyncLRU(maxsize=128)
        async def fetch_data(x):
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.01)
            return x * 2
        
        async def _test():
            # First call should execute
            r1 = await fetch_data(5)
            self.assertEqual(r1, 10)
            self.assertEqual(call_count, 1)
            
            # Second call with same arg should hit cache
            r2 = await fetch_data(5)
            self.assertEqual(r2, 10)
            self.assertEqual(call_count, 1)  # No new call
            
            # Different arg should execute
            r3 = await fetch_data(10)
            self.assertEqual(r3, 20)
            self.assertEqual(call_count, 2)
        
        asyncio.run(_test())
    
    def test_ttl_decorator_basic(self):
        """Basic TTL decorator functionality."""
        call_count = 0
        
        @AsyncTTL(time_to_live=60)
        async def fetch_data(x):
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.01)
            return x * 3
        
        async def _test():
            r1 = await fetch_data(5)
            self.assertEqual(r1, 15)
            self.assertEqual(call_count, 1)
            
            r2 = await fetch_data(5)
            self.assertEqual(r2, 15)
            self.assertEqual(call_count, 1)  # Cached
        
        asyncio.run(_test())
    
    def test_decorator_with_skip_args(self):
        """Decorator with skip_args for methods."""
        call_count = 0
        
        class MyClass:
            @AsyncLRU(maxsize=128, skip_args=1)
            async def method(self, x):
                nonlocal call_count
                call_count += 1
                return x * 2
        
        async def _test():
            obj1 = MyClass()
            obj2 = MyClass()
            
            # Same x, different self - should hit cache (self is skipped)
            r1 = await obj1.method(5)
            r2 = await obj2.method(5)
            self.assertEqual(r1, r2)
            self.assertEqual(call_count, 1)
        
        asyncio.run(_test())


class TestDirectCacheUsage(unittest.TestCase):
    """Test using AsyncCache directly (not via decorators)."""
    
    def test_basic_get_set(self):
        """Basic get/set operations."""
        async def _test():
            cache = AsyncCache(maxsize=100)
            
            # Set and get
            cache.set('key1', 'value1')
            result = await cache.get('key1')
            self.assertEqual(result, 'value1')
            
            # Update
            cache.set('key1', 'value2')
            result = await cache.get('key1')
            self.assertEqual(result, 'value2')
        
        asyncio.run(_test())
    
    def test_get_with_loader(self):
        """Get with loader function."""
        async def _test():
            cache = AsyncCache()
            call_count = 0
            
            async def loader():
                nonlocal call_count
                call_count += 1
                return 'loaded_value'
            
            # First get should call loader
            result = await cache.get('key', loader=loader)
            self.assertEqual(result, 'loaded_value')
            self.assertEqual(call_count, 1)
            
            # Second get should hit cache
            result = await cache.get('key', loader=loader)
            self.assertEqual(result, 'loaded_value')
            self.assertEqual(call_count, 1)  # No new load
        
        asyncio.run(_test())
    
    def test_cache_miss_without_loader(self):
        """Cache miss without loader returns None."""
        async def _test():
            cache = AsyncCache()
            result = await cache.get('nonexistent')
            self.assertIsNone(result)
        
        asyncio.run(_test())
    
    def test_delete_operation(self):
        """Delete removes key from cache."""
        async def _test():
            cache = AsyncCache()
            cache.set('key', 'value')
            self.assertEqual(await cache.get('key'), 'value')
            
            cache.delete('key')
            self.assertIsNone(await cache.get('key'))
        
        asyncio.run(_test())
    
    def test_delete_nonexistent_key(self):
        """Delete nonexistent key doesn't raise error."""
        async def _test():
            cache = AsyncCache()
            cache.delete('nonexistent')  # Should not raise
        
        asyncio.run(_test())
    
    def test_clear_operation(self):
        """Clear removes all keys."""
        async def _test():
            cache = AsyncCache()
            cache.set('key1', 'value1')
            cache.set('key2', 'value2')
            
            cache.clear()
            
            self.assertIsNone(await cache.get('key1'))
            self.assertIsNone(await cache.get('key2'))
            self.assertEqual(len(cache.cache), 0)
        
        asyncio.run(_test())


class TestThunderingHerdProtection(unittest.TestCase):
    """Test thundering herd protection for concurrent cache misses."""
    
    def test_single_loader_for_concurrent_misses(self):
        """Only one loader should execute for concurrent misses on same key."""
        async def _test():
            cache = AsyncCache()
            loader_calls = 0
            
            async def loader():
                nonlocal loader_calls
                loader_calls += 1
                await asyncio.sleep(0.1)  # Slow load
                return 'value'
            
            # 50 concurrent requests for same key
            tasks = [cache.get('key', loader=loader) for _ in range(50)]
            results = await asyncio.gather(*tasks)
            
            # All should get same value
            self.assertTrue(all(r == 'value' for r in results))
            # But only 1 loader call
            self.assertEqual(loader_calls, 1)
        
        asyncio.run(_test())
    
    def test_herd_protection_with_error(self):
        """Herd protection should propagate errors to all waiters."""
        async def _test():
            cache = AsyncCache()
            
            async def failing_loader():
                await asyncio.sleep(0.05)
                raise ValueError("Load failed")
            
            # Concurrent requests
            tasks = [cache.get('key', loader=failing_loader) for _ in range(10)]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # All should get the error
            for r in results:
                self.assertIsInstance(r, ValueError)
                self.assertEqual(str(r), "Load failed")
        
        asyncio.run(_test())
    
    def test_no_herd_for_different_keys(self):
        """Different keys should have independent loaders."""
        async def _test():
            cache = AsyncCache()
            loader_calls = {}
            
            async def loader(key):
                loader_calls[key] = loader_calls.get(key, 0) + 1
                await asyncio.sleep(0.05)
                return f'value-{key}'
            
            # Concurrent requests for different keys
            tasks = [
                cache.get('key1', loader=lambda: loader('key1')),
                cache.get('key2', loader=lambda: loader('key2')),
                cache.get('key3', loader=lambda: loader('key3')),
            ]
            results = await asyncio.gather(*tasks)
            
            # Each key should have its own loader call
            self.assertEqual(loader_calls['key1'], 1)
            self.assertEqual(loader_calls['key2'], 1)
            self.assertEqual(loader_calls['key3'], 1)
        
        asyncio.run(_test())


class TestBatchLoader(unittest.TestCase):
    """Test DataLoader-style batch loading."""
    
    def test_batch_loader_basic(self):
        """Basic batch loader functionality."""
        async def _test():
            cache = AsyncCache(batch_window_ms=10, max_batch_size=10)
            batch_calls = 0
            
            async def batch_loader(keys):
                nonlocal batch_calls
                batch_calls += 1
                return [f'value-{k}' for k in keys]
            
            # Multiple concurrent gets
            tasks = [cache.get(f'key{i}', batch_loader=batch_loader) for i in range(5)]
            results = await asyncio.gather(*tasks)
            
            # Should be batched into single call
            self.assertEqual(batch_calls, 1)
            self.assertEqual(results, ['value-key0', 'value-key1', 'value-key2', 'value-key3', 'value-key4'])
        
        asyncio.run(_test())
    
    def test_batch_loader_respects_max_size(self):
        """Batch loader respects max_batch_size."""
        async def _test():
            cache = AsyncCache(batch_window_ms=100, max_batch_size=3)
            batch_calls = 0
            keys_per_batch = []
            
            async def batch_loader(keys):
                nonlocal batch_calls
                batch_calls += 1
                keys_per_batch.append(len(keys))
                return [f'value-{k}' for k in keys]
            
            # 7 requests with max_batch_size=3 should create 3 batches
            tasks = [cache.get(f'key{i}', batch_loader=batch_loader) for i in range(7)]
            await asyncio.gather(*tasks)
            
            self.assertEqual(batch_calls, 3)  # 3 + 3 + 1
            self.assertEqual(keys_per_batch, [3, 3, 1])
        
        asyncio.run(_test())
    
    def test_batch_loader_returns_dict(self):
        """Batch loader can return dict instead of list."""
        async def _test():
            cache = AsyncCache(batch_window_ms=10)
            
            async def batch_loader(keys):
                return {k: f'value-{k}' for k in keys}
            
            tasks = [cache.get(f'key{i}', batch_loader=batch_loader) for i in range(3)]
            results = await asyncio.gather(*tasks)
            
            self.assertEqual(results, ['value-key0', 'value-key1', 'value-key2'])
        
        asyncio.run(_test())
    
    def test_batch_loader_error_handling(self):
        """Errors in batch loader propagate to all waiters."""
        async def _test():
            cache = AsyncCache(batch_window_ms=10)
            
            async def failing_batch_loader(keys):
                raise ValueError("Batch load failed")
            
            tasks = [cache.get(f'key{i}', batch_loader=failing_batch_loader) for i in range(3)]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for r in results:
                self.assertIsInstance(r, ValueError)
        
        asyncio.run(_test())


class TestCacheWarmup(unittest.TestCase):
    """Test cache warmup functionality."""
    
    def test_warmup_basic(self):
        """Basic warmup loads all keys."""
        async def _test():
            cache = AsyncCache()
            loaded_keys = []
            
            async def loader(key):
                loaded_keys.append(key)
                return f'value-{key}'
            
            await cache.warmup({
                'key1': lambda: loader('key1'),
                'key2': lambda: loader('key2'),
                'key3': lambda: loader('key3'),
            })
            
            self.assertEqual(set(loaded_keys), {'key1', 'key2', 'key3'})
            
            # All should be in cache
            self.assertEqual(await cache.get('key1'), 'value-key1')
            self.assertEqual(await cache.get('key2'), 'value-key2')
            self.assertEqual(await cache.get('key3'), 'value-key3')
        
        asyncio.run(_test())
    
    def test_warmup_with_existing_keys(self):
        """Warmup doesn't overwrite existing keys."""
        async def _test():
            cache = AsyncCache()
            cache.set('existing', 'old_value')
            
            async def loader():
                return 'new_value'
            
            await cache.warmup({'existing': loader})
            
            # Should still have old value (warmup uses get with loader)
            # Actually, warmup calls get which will hit cache
            result = await cache.get('existing')
            self.assertEqual(result, 'old_value')
        
        asyncio.run(_test())


class TestTTLEdgeCases(unittest.TestCase):
    """Test TTL handling edge cases."""
    
    def test_ttl_expiration(self):
        """Keys expire after TTL."""
        async def _test():
            cache = AsyncCache(default_ttl=1)
            cache.set('key', 'value')
            
            self.assertEqual(await cache.get('key'), 'value')
            
            time.sleep(1.1)
            
            self.assertIsNone(await cache.get('key'))
        
        asyncio.run(_test())
    
    def test_ttl_override(self):
        """Per-key TTL overrides default."""
        async def _test():
            cache = AsyncCache(default_ttl=10)
            cache.set('short', 'value', ttl=1)
            cache.set('long', 'value', ttl=10)
            
            time.sleep(1.1)
            
            self.assertIsNone(await cache.get('short'))
            self.assertEqual(await cache.get('long'), 'value')
        
        asyncio.run(_test())
    
    def test_no_ttl(self):
        """ttl=None means no expiration."""
        async def _test():
            cache = AsyncCache(default_ttl=1)
            cache.set('key', 'value', ttl=None)
            
            time.sleep(1.1)
            
            self.assertEqual(await cache.get('key'), 'value')
        
        asyncio.run(_test())
    
    def test_ttl_check_on_contains(self):
        """TTL check happens when checking contains."""
        async def _test():
            cache = AsyncCache(default_ttl=1)
            cache.set('key', 'value')
            
            time.sleep(1.1)
            
            # Check should trigger expiration
            self.assertFalse('key' in cache.cache)
        
        asyncio.run(_test())


class TestLRUEviction(unittest.TestCase):
    """Test LRU eviction edge cases."""
    
    def test_lru_eviction_order(self):
        """Least recently used items are evicted first."""
        async def _test():
            cache = AsyncCache(maxsize=3)
            
            cache.set('a', 1)
            cache.set('b', 2)
            cache.set('c', 3)
            
            # Access 'a' to make it most recently used
            await cache.get('a')
            
            # Add new item, should evict 'b' (least recently used)
            cache.set('d', 4)
            
            self.assertEqual(await cache.get('a'), 1)  # Still there
            self.assertIsNone(await cache.get('b'))     # Evicted
            self.assertEqual(await cache.get('c'), 3)  # Still there
            self.assertEqual(await cache.get('d'), 4)  # New
        
        asyncio.run(_test())
    
    def test_maxsize_none_unlimited(self):
        """maxsize=None means unlimited cache."""
        async def _test():
            cache = AsyncCache(maxsize=None)
            
            # Add many items
            for i in range(1000):
                cache.set(f'key{i}', i)
            
            # All should be there
            self.assertEqual(len(cache.cache), 1000)
        
        asyncio.run(_test())


class TestMetrics(unittest.TestCase):
    """Test metrics accuracy."""
    
    def test_metrics_basic(self):
        """Basic metrics tracking."""
        async def _test():
            cache = AsyncCache()
            
            # Miss
            await cache.get('key1', loader=lambda: asyncio.sleep(0.01) or 'value1')
            
            # Hit
            await cache.get('key1')
            
            # Another miss
            await cache.get('key2', loader=lambda: asyncio.sleep(0.01) or 'value2')
            
            metrics = cache.get_metrics()
            self.assertEqual(metrics['hits'], 1)
            self.assertEqual(metrics['misses'], 2)
            self.assertEqual(metrics['size'], 2)
            self.assertAlmostEqual(metrics['hit_rate'], 1/3, places=2)
        
        asyncio.run(_test())
    
    def test_metrics_after_clear(self):
        """Metrics reset after clear."""
        async def _test():
            cache = AsyncCache()
            
            await cache.get('key', loader=lambda: asyncio.sleep(0.01) or 'value')
            await cache.get('key')  # hit
            
            cache.clear()
            
            metrics = cache.get_metrics()
            self.assertEqual(metrics['hits'], 0)
            self.assertEqual(metrics['misses'], 0)
        
        asyncio.run(_test())
    
    def test_metrics_empty_cache(self):
        """Metrics with no operations."""
        cache = AsyncCache()
        metrics = cache.get_metrics()
        
        self.assertEqual(metrics['hits'], 0)
        self.assertEqual(metrics['misses'], 0)
        self.assertEqual(metrics['size'], 0)
        self.assertEqual(metrics['hit_rate'], 0.0)


class TestErrorHandling(unittest.TestCase):
    """Test error handling in various scenarios."""
    
    def test_loader_exception_propagates(self):
        """Loader exceptions propagate to caller."""
        async def _test():
            cache = AsyncCache()
            
            async def failing_loader():
                raise ValueError("Load failed")
            
            with self.assertRaises(ValueError) as ctx:
                await cache.get('key', loader=failing_loader)
            
            self.assertEqual(str(ctx.exception), "Load failed")
        
        asyncio.run(_test())
    
    def test_cache_usable_after_loader_failure(self):
        """Cache remains usable after loader failure."""
        async def _test():
            cache = AsyncCache()
            
            async def failing_loader():
                raise ValueError("Load failed")
            
            async def success_loader():
                return 'success'
            
            # First call fails
            try:
                await cache.get('key', loader=failing_loader)
            except ValueError:
                pass
            
            # Second call with different loader should work
            result = await cache.get('key', loader=success_loader)
            self.assertEqual(result, 'success')
        
        asyncio.run(_test())


class TestConcurrentAccessPatterns(unittest.TestCase):
    """Test various concurrent access patterns."""
    
    def test_mixed_read_write(self):
        """Mixed read and write operations."""
        async def _test():
            cache = AsyncCache(maxsize=100)
            errors = []
            
            async def writer(i):
                try:
                    cache.set(f'key{i}', f'value{i}')
                except Exception as e:
                    errors.append(('write', i, str(e)))
            
            async def reader(i):
                try:
                    await cache.get(f'key{i}')
                except Exception as e:
                    errors.append(('read', i, str(e)))
            
            # Mix of reads and writes
            tasks = []
            for i in range(100):
                tasks.append(writer(i))
                tasks.append(reader(i))
                if i % 10 == 0:
                    tasks.append(asyncio.create_task(asyncio.to_thread(cache.clear)))
            
            await asyncio.gather(*tasks)
            
            self.assertEqual(len(errors), 0, f"Errors occurred: {errors[:3]}")
        
        asyncio.run(_test())
    
    def test_rapid_cache_clear_during_access(self):
        """Rapid cache clears during active access."""
        async def _test():
            cache = AsyncCache()
            errors = []
            
            async def access():
                try:
                    cache.set('key', 'value')
                    await cache.get('key')
                    cache.get_metrics()
                except Exception as e:
                    errors.append(str(e))
            
            def clear():
                try:
                    cache.clear()
                except Exception as e:
                    errors.append(str(e))
            
            tasks = [access() for _ in range(50)]
            clear_tasks = [asyncio.to_thread(clear) for _ in range(10)]
            
            await asyncio.gather(*tasks, *clear_tasks)
            
            self.assertEqual(len(errors), 0)
        
        asyncio.run(_test())


if __name__ == '__main__':
    unittest.main(verbosity=2)