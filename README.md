# async-cache
**A LRU cache for asyncio**

**Basic Usage:**

```
from async-cache import AsyncLRU

@AsyncLRU(maxsize=128)
async def func(*args, **kwargs):
    pass
```

