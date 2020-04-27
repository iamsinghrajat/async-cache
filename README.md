# async-cache
**A LRU cache for asyncio**

**Basic Usage:**

```from async_lru import AsyncCache
import AsyncCache

@AsyncCache(maxsize=128)
async def func(*args, **kwargs):
    pass
```

