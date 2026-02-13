import asyncio
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, Request, Body
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from cache.async_cache import AsyncCache
from cache.async_lru import AsyncLRU
from cache.async_ttl import AsyncTTL

app = FastAPI(title="Async-Cache Test UI")

app.mount("/static", StaticFiles(directory="demo/static"), name="static")
templates = Jinja2Templates(directory="demo/templates")

# Globals for persistent cache instances across requests (to allow metrics, hits/misses accumulate)
ttl_decorator: Optional[AsyncTTL] = None
lru_decorator: Optional[AsyncLRU] = None
direct_cache: Optional[AsyncCache] = None
ttl_func = None
lru_func = None

class CacheConfig(BaseModel):
    maxsize: int = 128
    ttl: Optional[int] = 60  # None for no expiration
    skip_args: int = 0
    batch_window_ms: int = 5
    max_batch_size: int = 100
    # use_cache per call, not global

async def simulate_data_load(key: str) -> str:
    """Simulate async data load (e.g., DB/API call) with 100ms latency to demo caching.
    On cache miss + single-loader: N calls (e.g., 100 * 100ms = 10s for unique keys).
    Herd protection or batch_loader: ~100ms total (1 DB call).
    """
    await asyncio.sleep(0.1)  # 100ms to resemble real DB call
    return f"data-for-{key}"

async def simulate_batch_load(keys: List[str]) -> List[str]:
    """Simulate batch data loader (single DB call for multiple keys, ~100ms total)."""
    await asyncio.sleep(0.1)  # 100ms for the batch
    return [f"data-for-{k}" for k in keys]

@app.get("/")
async def root(request: Request):
    """Serve the main UI."""
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/configure")
async def configure(config: CacheConfig = Body(...)):
    """Configure/recreate caches and decorated functions based on UI params.
    This allows testing different max_size, ttl, skip_args (now on LRU too), batch_*, use_cache etc.
    """
    global ttl_decorator, lru_decorator, direct_cache, ttl_func, lru_func

    # TTL decorator
    ttl_decorator = AsyncTTL(
        time_to_live=config.ttl,
        maxsize=config.maxsize,
        skip_args=config.skip_args
    )

    @ttl_decorator
    async def _ttl_func(key: str):
        # The wrapped func; key made by decorator using make_key (respects skip_args)
        return await simulate_data_load(key)

    ttl_func = _ttl_func

    # LRU decorator (now supports skip_args for parity with AsyncTTL)
    lru_decorator = AsyncLRU(maxsize=config.maxsize, skip_args=config.skip_args)

    @lru_decorator
    async def _lru_func(key: str):
        # The wrapped func; key made by decorator using make_key (respects skip_args)
        return await simulate_data_load(key)

    lru_func = _lru_func

    # Direct AsyncCache
    direct_cache = AsyncCache(
        maxsize=config.maxsize,
        default_ttl=config.ttl,
        batch_window_ms=config.batch_window_ms,
        max_batch_size=config.max_batch_size
    )

    return {"status": "configured", "config": config.dict()}

@app.post("/call/ttl")
async def call_ttl(data: Dict[str, Any] = Body(...)):
    """Single call via @AsyncTTL decorator. Supports use_cache param for force miss."""
    if ttl_func is None:
        await configure(CacheConfig())  # default if not configured
    key = data.get("key")
    use_cache = data.get("use_cache", True)
    result = await ttl_func(key, use_cache=use_cache)
    return {"result": result, "type": "ttl"}

@app.post("/call/lru")
async def call_lru(data: Dict[str, Any] = Body(...)):
    """Single call via @AsyncLRU decorator."""
    if lru_func is None:
        await configure(CacheConfig())
    key = data.get("key")
    use_cache = data.get("use_cache", True)
    result = await lru_func(key, use_cache=use_cache)
    return {"result": result, "type": "lru"}

@app.post("/call/cache")
async def call_cache(data: Dict[str, Any] = Body(...)):
    """Direct use of AsyncCache class. Supports single loader (herd prot) or batch_loader."""
    if direct_cache is None:
        await configure(CacheConfig())
    key = data.get("key")
    use_batch = data.get("use_batch", False)
    if use_batch:
        # batch data loader for thundering herd on batch + efficiency for multi keys
        async def batch_loader(ks):
            return await simulate_batch_load(ks)
        result = await direct_cache.get(key, batch_loader=batch_loader)
        ctype = "direct-batch"
    else:
        # single loader for herd protection
        async def loader():
            return await simulate_data_load(key)
        result = await direct_cache.get(key, loader=loader)
        ctype = "direct-single"
    return {"result": result, "type": ctype}

@app.get("/metrics/{cache_type}")
async def get_metrics(cache_type: str):
    """Get metrics: hits, misses, hit_rate, size. Used after tests to show hit ratio etc."""
    if cache_type == "ttl" and ttl_decorator:
        return ttl_decorator.cache.get_metrics()  # or ttl_func.get_metrics()
    elif cache_type == "lru" and lru_decorator:
        return lru_decorator.cache.get_metrics()
    elif cache_type == "direct" and direct_cache:
        return direct_cache.get_metrics()
    return {"hits": 0, "misses": 0, "hit_rate": 0.0, "size": 0}

@app.post("/clear/{cache_type}")
async def clear_cache(cache_type: str):
    """Clear cache to reset for new tests."""
    if cache_type == "ttl" and ttl_decorator:
        ttl_decorator.clear_cache()
    elif cache_type == "lru" and lru_decorator:
        lru_decorator.clear_cache()
    elif cache_type == "direct" and direct_cache:
        direct_cache.clear()
    return {"status": "cleared", "type": cache_type}

@app.post("/set/cache")
async def set_cache(data: Dict[str, Any] = Body(...)):
    """Direct set for testing."""
    if direct_cache is None:
        await configure(CacheConfig())
    key = data.get("key")
    value = data.get("value")
    ttl = data.get("ttl")
    direct_cache.set(key, value, ttl=ttl)
    return {"status": "set", "key": key}

@app.post("/warmup/cache")
async def warmup_cache(data: Dict[str, Any] = Body(...)):
    """Test warmup feature with list of keys."""
    if direct_cache is None:
        await configure(CacheConfig())
    keys: List[str] = data.get("keys", [])
    keys_with_loaders = {}
    for k in keys:
        # Closure for loader per key
        async def loader(k=k):
            return await simulate_data_load(k)
        keys_with_loaders[k] = loader
    await direct_cache.warmup(keys_with_loaders)
    metrics = direct_cache.get_metrics()
    return {"status": "warmed", "keys": keys, "metrics": metrics}

@app.post("/delete/cache")
async def delete_cache(data: Dict[str, Any] = Body(...)):
    """Test delete."""
    if direct_cache is None:
        await configure(CacheConfig())
    key = data.get("key")
    direct_cache.delete(key)
    return {"status": "deleted", "key": key}
