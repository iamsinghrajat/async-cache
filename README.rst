async-cache
===========
:info: A caching solution for asyncio

.. image:: https://travis-ci.org/iamsinghrajat/async-cache.svg?branch=master
    :target: https://travis-ci.org/iamsinghrajat/async-cache
.. image:: https://img.shields.io/pypi/v/async-cache.svg
    :target: https://pypi.python.org/pypi/async-cache
.. image:: https://www.codetriage.com/iamsinghrajat/async-cache/badges/users.svg
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
        """
        maxsize : max number of results that are cached.
                  if  max limit  is reached the oldest result  is deleted.
        """
        pass
    
    
    # TTL Cache
    from cache import AsyncTTL
    
    @AsyncTTL(time_to_live=60, min_cleanup_interval=60)
    async def func(*args, **kwargs):
        """
        time_to_live : max time for which a cached result  is valid
        min_cleanup_interval : time interval at which all expired  results will be cleaned automatically
                               by default they are cleaned when function is called with result's key again.
        """
        pass

    # Supports primitive as well as non-primitive function parameter.
    # Currently TTL & LRU cache is supported.

Advanced Usage
-----------

.. code-block:: python
    
    class DbModel:
        id: int
        value: int
        
    
    from cache import AsyncLRU
    
    @AsyncLRU(maxsize=128)
    async def func(model: "DbModel"):
        ...
        # function logic
        ...
    
    # async-cache will work even if function parameters are 
    # orm objects or request object or of any other custom type.
    
    


