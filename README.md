# async-cache
**A caching solution for asyncio**

**Basic Usage:**

```
from async-cache import AsyncLRU

@AsyncLRU(maxsize=128)
async def func(*args, **kwargs):
    pass
```

`async-cache also supports primitive as well as non-primitive function parameter.`
`Currently only LRU cache is supported.`