"""monocle/rate_limit.py — Shared slowapi Limiter instance."""
import os

from slowapi import Limiter
from slowapi.util import get_remote_address

# Use environment variable to disable rate limiting in tests
# Can be set via: export MONOCLE_DISABLE_RATE_LIMIT=1
# Or pytest can set it via conftest
_DISABLE_LIMITS = os.getenv("MONOCLE_DISABLE_RATE_LIMIT", "").lower() in ("1", "true", "yes")

if _DISABLE_LIMITS:
    # In test mode, create a no-op limiter that doesn't actually rate limit
    class NoOpLimiter:
        def limit(self, *args, **kwargs):
            """No-op decorator that passes through the function unchanged."""
            def decorator(func):
                return func
            return decorator
    
    limiter = NoOpLimiter()
else:
    limiter = Limiter(key_func=get_remote_address)
