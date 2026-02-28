async-cache
===========

.. image:: https://img.shields.io/pypi/v/async-cache.svg
    :target: https://pypi.python.org/pypi/async-cache
.. image:: https://img.shields.io/readthedocs/async-cache/latest.svg
    :target: https://async-cache.readthedocs.io/en/latest/
.. image:: https://img.shields.io/pypi/dm/async-cache
    :target: https://pypi.python.org/pypi/async-cache

**Production-ready asyncio cache with thundering herd protection, batch loading, and comprehensive metrics.**

async-cache is a high-performance, in-memory application-layer cache designed for asyncio-based microservices. It solves critical caching challenges like thundering herd protection, batch loading (DataLoader pattern), and cache warming—making it ideal for high-throughput services where cache efficiency directly impacts database load and response latency.

.. contents:: Table of Contents
   :depth: 2
   :local:

Installation
------------

.. code-block:: bash

    pip install async-cache

Requires Python 3.8+.

Why async-cache?
----------------

**Problem: Caching in async microservices is hard**

- **Thundering herd**: When cache expires, 1000 concurrent requests can overwhelm your database
- **N+1 queries**: Loading related data efficiently without batching kills performance  
- **Cold starts**: Empty cache after restart causes latency spikes
- **Observability**: No visibility into cache effectiveness

**Solution: async-cache provides these out of the box**

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Feature
     - Benefit
   * - Thundering Herd Protection
     - Only 1 backend call even with 1000 concurrent cache misses
   * - DataLoader Batching
     - Automatic batching of concurrent requests (N+1 → 1 query)
   * - Cache Warmup
     - Preload hot data at startup to avoid cold starts
   * - Metrics & Observability
     - Built-in hit rates for monitoring and optimization
   * - Flexible TTL
     - Per-key TTL with global defaults
   * - LRU Eviction
     - Automatic eviction of least-recently-used items

Quick Start
-----------

Basic Usage
~~~~~~~~~~~

.. code-block:: python

    import asyncio
    from cache import AsyncCache

    cache = AsyncCache(maxsize=1000, default_ttl=300)

    async def get_user(user_id: int) -> dict:
        """Get user with automatic caching."""
        return await cache.get(
            f"user:{user_id}",
            loader=lambda: fetch_from_database(user_id)
        )

Decorator Usage
~~~~~~~~~~~~~~~

.. code-block:: python

    from cache import AsyncLRU, AsyncTTL

    @AsyncLRU(maxsize=128)
    async def get_product(product_id: int):
        return await db.query_product(product_id)

    @AsyncTTL(time_to_live=60)  # 60 second TTL
    async def get_session(session_id: str):
        return await db.get_session(session_id)

Core Features
-------------

Thundering Herd Protection
~~~~~~~~~~~~~~~~~~~~~~~~~~

When a cached item expires under heavy load, multiple concurrent requests can trigger duplicate database queries (thundering herd). async-cache ensures only **one** loader executes while others wait for the result.

.. code-block:: python

    # 1000 concurrent requests, only 1 database query
    tasks = [get_user(123) for _ in range(1000)]
    results = await asyncio.gather(*tasks)

DataLoader-Style Batching
~~~~~~~~~~~~~~~~~~~~~~~~~

Automatically batch concurrent requests to reduce database round-trips. Perfect for GraphQL resolvers or loading related entities.

.. code-block:: python

    async def batch_load_users(user_ids: list[int]) -> list[dict]:
        """Load multiple users in a single query."""
        return await db.query_users_in_batch(user_ids)

    # These two calls are automatically batched into one query
    user1, user2 = await asyncio.gather(
        cache.get(1, batch_loader=batch_load_users),
        cache.get(2, batch_loader=batch_load_users)
    )

Cache Warmup
~~~~~~~~~~~~

Preload critical data at application startup to avoid cold-start latency.

.. code-block:: python

    async def startup():
        await cache.warmup({
            "config:app": load_app_config,
            "feature_flags": load_feature_flags,
            "popular:products": load_popular_products,
        })

Metrics & Observability
~~~~~~~~~~~~~~~~~~~~~~~

Built-in metrics for monitoring cache performance and optimizing TTL values.

.. code-block:: python

    metrics = cache.get_metrics()
    print(f"Hit rate: {metrics['hit_rate']:.1%}")
    print(f"Size: {metrics['size']}")
    print(f"Hits/Misses: {metrics['hits']}/{metrics['misses']}")

TTL & Invalidation
~~~~~~~~~~~~~~~~~~

Flexible time-to-live with global defaults and per-key overrides.

.. code-block:: python

    # Global default TTL
    cache = AsyncCache(default_ttl=300)  # 5 minutes

    # Per-key override
    await cache.set("session:123", data, ttl=3600)  # 1 hour
    await cache.set("temp:data", data, ttl=60)      # 1 minute
    await cache.set("permanent:data", data, ttl=None)  # No expiration

    # Manual invalidation
    await cache.delete("session:123")
    cache.clear()  # Clear all

Advanced Usage
--------------

Per-Key TTL Override
~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

    async def get_data(key: str, cache_minutes: int = 5):
        return await cache.get(
            key,
            loader=lambda: expensive_query(key),
            ttl=cache_minutes * 60
        )

Skip Arguments in Cache Key
~~~~~~~~~~~~~~~~~~~~~~~~~~~

For class methods, skip `self` from the cache key:

.. code-block:: python

    class UserService:
        @AsyncLRU(maxsize=100, skip_args=1)  # Skip 'self'
        async def get_user(self, user_id: int):
            return await self.db.get_user(user_id)

Force Refresh
~~~~~~~~~~~~~

Bypass cache and force a fresh load:

.. code-block:: python

    @AsyncTTL(time_to_live=60)
    async def get_status():
        return await check_service_status()

    # Force fresh check
    status = await get_status(use_cache=False)

Configuration Options
---------------------

AsyncCache Parameters
~~~~~~~~~~~~~~~~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 20 15 65

   * - Parameter
     - Default
     - Description
   * - maxsize
     - 128
     - Maximum number of items in cache (None = unlimited)
   * - default_ttl
     - None
     - Default TTL in seconds (None = no expiration)
   * - batch_window_ms
     - 5
     - Window for batching concurrent requests (milliseconds)
   * - max_batch_size
     - 100
     - Maximum batch size for DataLoader pattern

Decorator Parameters
~~~~~~~~~~~~~~~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 20 15 65

   * - Parameter
     - Default
     - Description
   * - maxsize (AsyncLRU)
     - 128
     - Maximum cache size
   * - time_to_live (AsyncTTL)
     - 60
     - TTL in seconds
   * - skip_args
     - 0
     - Number of initial args to skip in cache key (for self/cls)

API Reference
-------------

See :doc:`api` for complete API documentation.

Best Practices
--------------

1. **Use thundering herd protection** for hot keys under heavy load
2. **Enable batching** for GraphQL resolvers or related entity loading
3. **Warmup critical data** at application startup
4. **Monitor metrics** to tune TTL and maxsize values
5. **Use appropriate TTLs** - short for volatile data, long for static data

Performance Characteristics
---------------------------

- **Get/Set**: O(1) average case
- **Memory**: O(n) where n is maxsize
- **Thundering herd**: O(1) loader calls regardless of concurrent requests
- **Batching**: Automatic within configured window

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`