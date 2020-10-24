async-cache
===========
:info: A caching solution for asyncio

.. image:: https://travis-ci.org/iamsinghrajat/async-cache.svg?branch=master
    :target: https://travis-ci.org/iamsinghrajat/async-cache
.. image:: https://img.shields.io/pypi/v/async-cache.svg
    :target: https://pypi.python.org/pypi/async-cache

Installation
------------

.. code-block:: shell

    pip install async-cache

Basic Usage
-----------

.. code-block:: python
    
    # LRU Cache
    from cache import AsyncLRU
    
    @AsyncLRU(maxsize=128)
    async def func(*args, **kwargs):
        pass
    
    
    # TTL Cache
    from cache import AsyncTTL
    
    @AsyncTTL(time_to_live=60, min_cleanup_interval=60)
    async def func(*args, **kwargs):
        pass


Supports primitive as well as non-primitive function parameter.

Currently TTL & LRU cache is supported.

