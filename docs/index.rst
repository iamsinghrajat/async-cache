async-cache
===========

.. image:: https://img.shields.io/pypi/v/async-cache.svg
    :target: https://pypi.python.org/pypi/async-cache
.. image:: https://img.shields.io/readthedocs/async-cache/latest.svg
    :target: https://async-cache.readthedocs.io/en/latest/
.. image:: https://img.shields.io/pypi/dm/async-cache
    :target: https://pypi.python.org/pypi/async-cache

A powerful, reliable in-memory application-layer cache for asyncio-based microservices and high-throughput services. 

async-cache goes beyond simple decorators to provide a robust caching backend with advanced features like thundering herd protection, batching, warmup, metrics, and TTL-based invalidation—designed for production microservices where cache efficiency directly impacts database load, latency, and scalability.

Installation
------------

.. code-block:: bash

    pip install async-cache

Quickstart: Function API (Recommended for Microservices)
-------------------------------------------------------

The core ``AsyncCache`` class provides a flexible, low-level API ideal for application-layer caching in services.

.. code-block:: python

    import asyncio
    from cache import AsyncCache

    cache = AsyncCache(maxsize=1000, default_ttl=300)  # 5 min TTL

    async def get_user(user_id):
        # cache.get with loader auto-caches on miss
        return await cache.get(
            f"user:{user_id}",
            loader=lambda: fetch_from_db(user_id),  # async loader
            ttl=60  # per-key override
        )

    # Preload hot keys at startup
    async def startup_warmup():
        await cache.warmup({
            "popular:key1": lambda: load_hot_data(1),
            "popular:key2": lambda: load_hot_data(2),
        })

    # Metrics for monitoring/observability
    print(cache.get_metrics())  # {'hits': 42, 'misses': 10, 'size': 50, 'hit_rate': 0.81}

Advanced Features
-----------------

Thundering Herd Protection
~~~~~~~~~~~~~~~~~~~~~~~~~~

Without protection, concurrent misses for the same key (e.g., popular item under load) would trigger duplicate backend calls, spiking DB load and latency.

With async-cache:

- Only one loader runs; others await the shared result.
- Critical for microservices under burst traffic.

.. code-block:: python

    # 100 concurrent calls to same key -> only 1 DB query
    tasks = [get_user(1) for _ in range(100)]
    results = await asyncio.gather(*tasks)

DataLoader-Style Batching
~~~~~~~~~~~~~~~~~~~~~~~~~

Group concurrent gets into batches to reduce DB roundtrips (e.g., batch user lookups).

.. code-block:: python

    async def batch_user_loader(user_ids):
        # one DB call for multiple IDs
        return {uid: await db_fetch(uid) for uid in user_ids}

    # auto-batches within window (configurable)
    await cache.get(1, batch_loader=batch_user_loader)
    await cache.get(2, batch_loader=batch_user_loader)  # grouped

Cache Warmup
~~~~~~~~~~~~

Preload popular keys at startup to avoid cold-start misses in microservices.

.. code-block:: python

    await cache.warmup({key: loader for key, loader in hot_keys})

Metrics & Observability
~~~~~~~~~~~~~~~~~~~~~~~

Track hits/misses/size/hit_rate globally or per-function for decisions like TTL tuning or scaling.

.. code-block:: python

    metrics = cache.get_metrics()  # or func.get_metrics()
    # integrate with Prometheus, logs, etc.

Key-Based Invalidation & TTL
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Fine-grained control:

.. code-block:: python

    await cache.delete(key)  # or func.invalidate_cache(args)
    await cache.set(key, value, ttl=60)  # per-key TTL
    cache.clear()  # full reset

Decorator Convenience
~~~~~~~~~~~~~~~~~~~~~

For simple cases, use as decorator (thin wrapper over core API):

.. code-block:: python

    from cache import AsyncLRU, AsyncTTL

    @AsyncLRU(maxsize=128)
    async def func(*args):
        ...

    # or with TTL + skip_args for methods
    @AsyncTTL(time_to_live=60, skip_args=1)
    async def method(self, arg):
        ...

Full API Reference
------------------

See :doc:`api` for details.

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
EOF