import time
from typing import Any, Dict, Optional, Tuple


class TTLCache:
    def __init__(self, default_ttl_sec: int = 300):
        self.default_ttl_sec = int(default_ttl_sec)
        self._store: Dict[str, Tuple[float, Any]] = {}

    def get(self, key: str) -> Optional[Any]:
        item = self._store.get(key)
        if not item:
            return None
        exp, val = item
        if time.time() > exp:
            self._store.pop(key, None)
            return None
        return val

    def set(self, key: str, value: Any, ttl_sec: Optional[int] = None) -> None:
        ttl = self.default_ttl_sec if ttl_sec is None else int(ttl_sec)
        self._store[key] = (time.time() + ttl, value)