async-cache
===========
:info: A caching solution for asyncio

.. image:: https://travis-ci.org/iamsinghrajat/async-cache.svg?branch=master
    :target: https://travis-ci.org/iamsinghrajat/async-cache
.. image:: https://img.shields.io/pypi/v/async-cache.svg
    :target: https://pypi.python.org/pypi/async-cache
.. image:: https://www.codetriage.com/iamsinghrajat/async-cache/badges/users.svg
    :target: https://pypi.python.org/pypi/async-cache
.. image:: https://static.pepy.tech/personalized-badge/async-cache?period=total&units=international_system&left_color=black&right_color=blue&left_text=Downloads
    :target: https://pepy.tech/project/async-cache
.. image:: https://snyk.io/advisor/python/async-cache/badge.svg
    :target: https://snyk.io/advisor/python/async-cache
    :alt: async-cache





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
        """
        maxsize : max number of results that are cached.
                  if  max limit  is reached the oldest result  is deleted.
        """
        pass
    
    
    # TTL Cache
    from cache import AsyncTTL
    
    @AsyncTTL(time_to_live=60, maxsize=1024)
    async def func(*args, **kwargs):
        """
        time_to_live : max time for which a cached result  is valid
        maxsize : max number of results that are cached.
                  if  max limit  is reached the oldest result  is deleted.
        """
        pass

    # Supports primitive as well as non-primitive function parameter.
    # Currently TTL & LRU cache is supported.

Advanced Usage
--------------

.. code-block:: python
    
    class CustomDataClass:
        id: int
        value: int
        
    
    from cache import AsyncLRU
    
    @AsyncLRU(maxsize=128)
    async def func(model: "CustomDataClass"):
        ...
        # function logic
        ...
    
    # async-cache will work even if function parameters are:
    #   1. orm objects
    #   2. request object
    #   3. any other custom object type.


    # If you want to refresh the function result use the `use_cache=False`
    # param in the function invocation
    func(*args, use_cache=False, **kwargs)
