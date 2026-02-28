import asyncio
import json
import os
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

# Add parent directory to path so 'cache' module can be found when running from demo/
_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

from cache.async_cache import AsyncCache
from cache.async_lru import AsyncLRU
from cache.async_ttl import AsyncTTL


# Globals for persistent cache instances across requests (to allow metrics, hits/misses accumulate)
ttl_decorator = None
lru_decorator = None
direct_cache = None
ttl_func = None
lru_func = None


async def simulate_data_load(key: str) -> str:
    """Simulate async data load (e.g., DB/API call) with 100ms latency to demo caching.
    On cache miss + single-loader: N calls (e.g., 100 * 100ms = 10s for unique keys).
    Herd protection or batch_loader: ~100ms total (1 DB call).
    """
    await asyncio.sleep(0.1)  # 100ms to resemble real DB call
    return f"data-for-{key}"


async def simulate_batch_load(keys: list) -> list:
    """Simulate batch data loader (single DB call for multiple keys, ~100ms total)."""
    await asyncio.sleep(0.1)  # 100ms for the batch
    return [f"data-for-{k}" for k in keys]


class CacheConfig:
    def __init__(self, data: dict):
        self.maxsize = data.get("maxsize", 128)
        self.ttl = data.get("ttl", 60)  # None for no expiration
        self.skip_args = data.get("skip_args", 0)
        self.batch_window_ms = data.get("batch_window_ms", 5)
        self.max_batch_size = data.get("max_batch_size", 100)


async def configure_caches(config: CacheConfig):
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

    return {"status": "configured", "config": {
        "maxsize": config.maxsize,
        "ttl": config.ttl,
        "skip_args": config.skip_args,
        "batch_window_ms": config.batch_window_ms,
        "max_batch_size": config.max_batch_size
    }}


async def call_ttl(data: dict):
    """Single call via @AsyncTTL decorator. Supports use_cache param for force miss."""
    global ttl_func
    if ttl_func is None:
        await configure_caches(CacheConfig({}))  # default if not configured
    key = data.get("key")
    use_cache = data.get("use_cache", True)
    result = await ttl_func(key, use_cache=use_cache)
    return {"result": result, "type": "ttl"}


async def call_lru(data: dict):
    """Single call via @AsyncLRU decorator."""
    global lru_func
    if lru_func is None:
        await configure_caches(CacheConfig({}))
    key = data.get("key")
    use_cache = data.get("use_cache", True)
    result = await lru_func(key, use_cache=use_cache)
    return {"result": result, "type": "lru"}


async def call_cache(data: dict):
    """Direct use of AsyncCache class. Supports single loader (herd prot) or batch_loader."""
    global direct_cache
    if direct_cache is None:
        await configure_caches(CacheConfig({}))
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


async def get_metrics(cache_type: str):
    """Get metrics: hits, misses, hit_rate, size. Used after tests to show hit ratio etc."""
    if cache_type == "ttl" and ttl_decorator:
        return ttl_decorator.cache.get_metrics()
    elif cache_type == "lru" and lru_decorator:
        return lru_decorator.cache.get_metrics()
    elif cache_type == "direct" and direct_cache:
        return direct_cache.get_metrics()
    return {"hits": 0, "misses": 0, "hit_rate": 0.0, "size": 0}


async def clear_cache(cache_type: str):
    """Clear cache to reset for new tests."""
    if cache_type == "ttl" and ttl_decorator:
        ttl_decorator.clear_cache()
    elif cache_type == "lru" and lru_decorator:
        lru_decorator.clear_cache()
    elif cache_type == "direct" and direct_cache:
        direct_cache.clear()
    return {"status": "cleared", "type": cache_type}


async def set_cache(data: dict):
    """Direct set for testing."""
    global direct_cache
    if direct_cache is None:
        await configure_caches(CacheConfig({}))
    key = data.get("key")
    value = data.get("value")
    ttl = data.get("ttl")
    direct_cache.set(key, value, ttl=ttl)
    return {"status": "set", "key": key}


async def warmup_cache(data: dict):
    """Test warmup feature with list of keys."""
    global direct_cache
    if direct_cache is None:
        await configure_caches(CacheConfig({}))
    keys = data.get("keys", [])
    keys_with_loaders = {}
    for k in keys:
        # Closure for loader per key
        async def loader(k=k):
            return await simulate_data_load(k)
        keys_with_loaders[k] = loader
    await direct_cache.warmup(keys_with_loaders)
    metrics = direct_cache.get_metrics()
    return {"status": "warmed", "keys": keys, "metrics": metrics}


async def delete_cache(data: dict):
    """Test delete."""
    global direct_cache
    if direct_cache is None:
        await configure_caches(CacheConfig({}))
    key = data.get("key")
    direct_cache.delete(key)
    return {"status": "deleted", "key": key}


def run_concurrency_tests():
    """Run concurrency tests and return results."""
    import sys
    import io
    from contextlib import redirect_stdout, redirect_stderr
    
    # Add tests directory to path
    tests_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "tests")
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    
    # Import and run tests
    from test_concurrency import TestConcurrencyEdgeCases
    import unittest
    
    # Capture output
    stdout_capture = io.StringIO()
    stderr_capture = io.StringIO()
    
    with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
        loader = unittest.TestLoader()
        suite = loader.loadTestsFromTestCase(TestConcurrencyEdgeCases)
        runner = unittest.TextTestRunner(verbosity=2, stream=stdout_capture)
        result = runner.run(suite)
    
    output = stdout_capture.getvalue()
    
    return {
        "tests_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "success": result.wasSuccessful(),
        "output": output,
        "failure_details": [
            {"test": str(f[0]), "error": str(f[1])} 
            for f in result.failures
        ],
        "error_details": [
            {"test": str(e[0]), "error": str(e[1])} 
            for e in result.errors
        ]
    }


def run_all_unit_tests():
    """Run all unit tests and return results."""
    import sys
    import io
    from contextlib import redirect_stdout, redirect_stderr
    
    # Add tests directory to path
    tests_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "tests")
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    
    import unittest
    
    # Capture output
    stdout_capture = io.StringIO()
    stderr_capture = io.StringIO()
    
    with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
        # Discover all tests in the tests directory
        loader = unittest.TestLoader()
        suite = loader.discover(tests_dir, pattern="test_*.py")
        runner = unittest.TextTestRunner(verbosity=2, stream=stdout_capture)
        result = runner.run(suite)
    
    output = stdout_capture.getvalue()
    
    return {
        "tests_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "success": result.wasSuccessful(),
        "output": output,
        "failure_details": [
            {"test": str(f[0]), "error": str(f[1])} 
            for f in result.failures
        ],
        "error_details": [
            {"test": str(e[0]), "error": str(e[1])} 
            for e in result.errors
        ]
    }


def run_test_suite(suite_name: str):
    """Run a specific test suite by name.
    
    Available suites:
    - 'core': Core async cache tests (test_async_cache.py)
    - 'features': Cache features tests (test_cache_features.py)
    - 'concurrency': Concurrency tests (test_concurrency.py)
    - 'edge_cases': Edge case and robustness tests (test_edge_cases.py)
    - 'lru': LRU decorator tests (test_lru.py)
    - 'ttl': TTL decorator tests (test_ttl.py)
    - 'all': All tests
    """
    import sys
    import io
    from contextlib import redirect_stdout, redirect_stderr
    
    # Add tests directory to path
    tests_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "tests")
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    
    import unittest
    
    suite_map = {
        'core': 'test_async_cache',
        'features': 'test_cache_features',
        'concurrency': 'test_concurrency',
        'edge_cases': 'test_edge_cases',
        'lru': 'test_lru',
        'ttl': 'test_ttl',
    }
    
    # Capture output
    stdout_capture = io.StringIO()
    stderr_capture = io.StringIO()
    
    with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
        loader = unittest.TestLoader()
        
        if suite_name == 'all':
            suite = loader.discover(tests_dir, pattern="test_*.py")
        elif suite_name in suite_map:
            module_name = suite_map[suite_name]
            try:
                module = __import__(module_name)
                suite = loader.loadTestsFromModule(module)
            except ImportError:
                # Try importing from tests package
                import importlib
                module = importlib.import_module(module_name)
                suite = loader.loadTestsFromModule(module)
        else:
            return {
                "error": f"Unknown suite: {suite_name}. Available: {list(suite_map.keys()) + ['all']}"
            }
        
        runner = unittest.TextTestRunner(verbosity=2, stream=stdout_capture)
        result = runner.run(suite)
    
    output = stdout_capture.getvalue()
    
    return {
        "suite": suite_name,
        "tests_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "success": result.wasSuccessful(),
        "output": output,
        "failure_details": [
            {"test": str(f[0]), "error": str(f[1])} 
            for f in result.failures
        ],
        "error_details": [
            {"test": str(e[0]), "error": str(e[1])} 
            for e in result.errors
        ]
    }


def run_async(coro):
    """Helper to run async functions in sync context."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    
    if loop and loop.is_running():
        # If we're already in an async context, create a new loop in a thread
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(asyncio.run, coro)
            return future.result()
    else:
        return asyncio.run(coro)


class RequestHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Suppress default logging
        pass

    def _send_json(self, data: dict, status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def _send_html(self, content: str, status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", "text/html")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(content.encode())

    def _read_json(self):
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length == 0:
            return {}
        body = self.rfile.read(content_length).decode()
        return json.loads(body) if body else {}

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/":
            # Serve the main UI
            template_path = os.path.join(os.path.dirname(__file__), "templates", "index.html")
            with open(template_path, "r") as f:
                content = f.read()
            self._send_html(content)
        elif path.startswith("/metrics/"):
            cache_type = path.split("/")[-1]
            result = run_async(get_metrics(cache_type))
            self._send_json(result)
        else:
            self._send_json({"error": "Not found"}, 404)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        data = self._read_json()

        try:
            if path == "/configure":
                config = CacheConfig(data)
                result = run_async(configure_caches(config))
                self._send_json(result)
            elif path == "/call/ttl":
                result = run_async(call_ttl(data))
                self._send_json(result)
            elif path == "/call/lru":
                result = run_async(call_lru(data))
                self._send_json(result)
            elif path == "/call/cache":
                result = run_async(call_cache(data))
                self._send_json(result)
            elif path.startswith("/clear/"):
                cache_type = path.split("/")[-1]
                result = run_async(clear_cache(cache_type))
                self._send_json(result)
            elif path == "/set/cache":
                result = run_async(set_cache(data))
                self._send_json(result)
            elif path == "/warmup/cache":
                result = run_async(warmup_cache(data))
                self._send_json(result)
            elif path == "/delete/cache":
                result = run_async(delete_cache(data))
                self._send_json(result)
            elif path == "/test/concurrency":
                result = run_concurrency_tests()
                self._send_json(result)
            elif path == "/test/all":
                result = run_all_unit_tests()
                self._send_json(result)
            elif path.startswith("/test/suite/"):
                suite_name = path.split("/")[-1]
                result = run_test_suite(suite_name)
                self._send_json(result)
            else:
                self._send_json({"error": "Not found"}, 404)
        except Exception as e:
            self._send_json({"error": str(e)}, 500)


def run_server(host: str = "0.0.0.0", port: int = 5001):
    server = HTTPServer((host, port), RequestHandler)
    print(f"Async-Cache Test UI running at http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server...")
        server.shutdown()


if __name__ == "__main__":
    run_server()
