import hashlib
import time

from fastapi import HTTPException, Request
from redis.exceptions import RedisError

from app.config import get_settings

# INCR + EXPIRE are atomic so a killed request cannot leave a permanent counter.
SCRIPT = """
local n = redis.call('INCR', KEYS[1])
if n == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
return n
"""


async def limit(request: Request, identity: str, maximum: int, seconds: int = 60):
    digest = hashlib.sha256(identity.encode()).hexdigest()
    key = f"stratum:limit:{digest}:{int(time.time()) // seconds}"
    try:
        count = await request.app.state.redis.eval(SCRIPT, 1, key, seconds)
    except RedisError as exc:
        if get_settings().redis_required:
            raise HTTPException(503, "Rate-limit service unavailable") from exc
        # Development-only local limiter. Production deliberately fails closed.
        counters = request.app.state.local_limits
        current = time.monotonic()
        for old in [k for k, (_, expiry) in counters.items() if expiry < current]:
            counters.pop(old, None)
        count = counters.get(key, (0, current + seconds))[0] + 1
        counters[key] = (count, current + seconds)
    if count > maximum:
        raise HTTPException(429, "Too many requests", headers={"Retry-After": str(seconds)})
