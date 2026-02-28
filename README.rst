async-cache
===========
:info: In-memory application layer cache

.. image:: https://img.shields.io/pypi/v/async-cache.svg
    :target: https://pypi.python.org/pypi/async-cache
.. image:: https://www.codetriage.com/iamsinghrajat/async-cache/badges/users.svg
    :target: https://pypi.python.org/pypi/async-cache
.. image:: https://static.pepy.tech/personalized-badge/async-cache?period=total&units=international_system&left_color=black&right_color=blue&left_text=Downloads
    :target: https://pepy.tech/project/async-cache





Installation
------------

.. code-block:: shell

    pip install async-cache

See full documentation at https://async-cache.readthedocs.io/

Core Usage: Function API for Microservices
------------------------------------------

Use ``AsyncCache`` for flexible caching:

.. code-block:: python

    from cache import AsyncCache

    cache = AsyncCache(maxsize=1000, default_ttl=300)  # TTL in seconds

    async def get_data(key):
        return await cache.get(
            key,
            loader=lambda: db_query(key),  # auto-caches on miss
        )

    # Warmup hot keys at startup
    await cache.warmup({"hot:key": lambda: preload_hot()})

    # Metrics for observability
    print(cache.get_metrics())  # hits, misses, size, hit_rate

Key Features & Examples
------------------------

**Thundering Herd Protection**
    Prevents duplicate work under concurrent load (e.g., popular keys). Without it, 100 misses = 100 DB hits; with it, = 1.

    .. code-block:: python

        cache = AsyncCache()
        async def loader(): 
            return await db_query()  # expensive
        # 100 concurrent -> 1 loader call
        results = await asyncio.gather(*[cache.get('key', loader=loader) for _ in range(100)])

**DataLoader-Style Batching**
    Groups concurrent gets into one batch call (reduces DB load; configurable window/size).

    .. code-block:: python

        async def batch_loader(keys):
            # one DB query for batch
            return {k: await db_batch_query(k) for k in keys}
        # auto-groups within 5ms window
        await asyncio.gather(
            cache.get(1, batch_loader=batch_loader),
            cache.get(2, batch_loader=batch_loader)
        )

**Cache Warmup**
    Preload at startup to avoid cold misses.

    .. code-block:: python

        await cache.warmup({
            "user:1": lambda: load_user(1),
            "config:global": lambda: load_config(),
        })

**Metrics**
    Observability for hit rate, size, etc. (global or per-function).

    .. code-block:: python

        metrics = cache.get_metrics()  # or func.get_metrics()
        # {'hits': 950, 'misses': 50, 'size': 200, 'hit_rate': 0.95}
        # Use for Prometheus/monitoring

**TTL & Invalidation**
    Per-key control + size-based eviction.

    .. code-block:: python

        await cache.set('key', value, ttl=60)  # override
        await cache.delete('key')  # or func.invalidate_cache(args)
        cache.clear()

Decorator Convenience
---------------------

For simple/readable code (uses core API under the hood):

.. code-block:: python

    from cache import AsyncLRU, AsyncTTL

    @AsyncLRU(maxsize=128)
    async def func(*args):
        ...

    @AsyncTTL(time_to_live=60, skip_args=1)  # e.g. skip 'self'
    async def method(self, arg):
        ...

Testing
-------

A local test dashboard is available for interactive testing:

.. code-block:: shell

    python demo/app.py  # Runs on http://localhost:5001

Use it to verify caching behavior, metrics, and concurrent load handling.

