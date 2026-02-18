import time
import threading
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

class TTLCache:
    """
    Cache simple in-memory con TTL.
    - Thread-safe para evitar colisiones en procesos asíncronos.
    - Limpieza automática de ítems expirados.
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
            
            # Si está expirado, lo borramos y devolvemos el default
            self._data.pop(key, None)
            return default

    def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> None:
        # Aseguramos que el valor no sea None para evitar confusiones al recuperar
        if value is None:
            return

        ttl = self.ttl if ttl_seconds is None else int(ttl_seconds)
        expires_at = self._now() + ttl
        
        with self._lock:
            # Si el cache está lleno, forzamos limpieza antes de insertar
            if len(self._data) >= self.max_items:
                self._evict_some()
            
            self._data[key] = (expires_at, value)

    def delete(self, key: str) -> None:
        with self._lock:
            self._data.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()
            logger.info("Cache limpiado por completo.")

    def _evict_some(self) -> None:
        """Estrategia de limpieza: Borra expirados y luego los más antiguos."""
        now = self._now()
        
        # 1. Borrar todos los que ya expiraron
        expired = [k for k, (exp, _) in self._data.items() if exp < now]
        for k in expired:
            self._data.pop(k, None)
        
        # 2. Si todavía estamos por encima del límite, borramos el 20% más viejo
        if len(self._data) >= self.max_items:
            # Ordenamos por tiempo de expiración (el más próximo a vencer primero)
            sorted_items = sorted(self._data.items(), key=lambda kv: kv[1][0])
            num_to_delete = max(1, int(len(sorted_items) * 0.2))
            for i in range(num_to_delete):
                self._data.pop(sorted_items[i][0], None)
            logger.debug(f"Evicción de cache: {num_to_delete} ítems eliminados.")
