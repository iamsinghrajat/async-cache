async-cache
===========
:info: A caching solution for asyncio

.. image:: https://img.shields.io/pypi/v/async-cache.svg
    :target: https://pypi.python.org/pypi/async-cache

Installation
------------

.. code-block:: shell

    pip install async-cache

Basic Usage
-----------

.. code-block:: python

    from async-cache import AsyncLRU
    
    @AsyncLRU(maxsize=128)
    async def func(*args, **kwargs):
        pass


Supports primitive as well as non-primitive function parameter.

Currently only LRU cache is supported.

