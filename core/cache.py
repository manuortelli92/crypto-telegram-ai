import time
import threading
from typing import Any, Optional


class TTLCache:
    """
    Cache simple in-memory con TTL.
    - Thread-safe (lock)
    - get/set
    - fallback opcional a "stale" (devuelve expirado si lo pedís)
    """

    def __init__(self, ttl_seconds: int = 60, max_items: int = 512):
        self.ttl = int(ttl_seconds)
        self.max_items = int(max_items)
        self._lock = threading.Lock()
        self._data = {}  # key -> (expires_at, value)

    def _now(self) -> float:
        return time.time()

    def get(self, key: str, default: Any = None, allow_stale: bool = False) -> Any:
        with self._lock:
            item = self._data.get(key)
            if not item:
                return default
            expires_at, value = item
            if allow_stale:
                return value
            if self._now() <= expires_at:
                return value
            # expirado -> borrar
            try:
                del self._data[key]
            except KeyError:
                pass
            return default

    def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> None:
        ttl = self.ttl if ttl_seconds is None else int(ttl_seconds)
        expires_at = self._now() + ttl
        with self._lock:
            # limpieza simple si se pasa del max
            if len(self._data) >= self.max_items:
                self._evict_some()
            self._data[key] = (expires_at, value)

    def delete(self, key: str) -> None:
        with self._lock:
            self._data.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()

    def _evict_some(self) -> None:
        # Estrategia simple: borra expirados primero, si sigue lleno borra los más viejos
        now = self._now()
        expired = [k for k, (exp, _) in self._data.items() if exp < now]
        for k in expired:
            self._data.pop(k, None)
        if len(self._data) < self.max_items:
            return

        # borrar los que vencen antes (más viejos)
        items = sorted(self._data.items(), key=lambda kv: kv[1][0])
        remove_n = max(1, len(items) - self.max_items + 1)
        for i in range(remove_n):
            self._data.pop(items[i][0], None)