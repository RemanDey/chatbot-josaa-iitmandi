import hashlib
import re

from cachetools import TTLCache


# Keep repeated admissions questions off the LLM for an hour to reduce latency
# and API pressure during counselling traffic spikes.
_cache = TTLCache(maxsize=512, ttl=3600)


def _key(prompt: str) -> str:
    # Normalize whitespace/case so tiny typing differences reuse the same reply.
    normalized = re.sub(r"\s+", " ", prompt.strip().lower())
    return hashlib.sha256(normalized.encode()).hexdigest()


def get_cached(prompt: str):
    return _cache.get(_key(prompt))


def set_cached(prompt: str, reply: str):
    _cache[_key(prompt)] = reply
