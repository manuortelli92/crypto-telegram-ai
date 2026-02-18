import time
import threading
import logging
from typing import Any, Optional, Dict, Tuple

# Configuración de diagnóstico
logger = logging.getLogger(__name__)

class TTLCache:
    """
    Caché de alto rendimiento para el OrtelliCryptoAI.
    Optimizado para evitar bloqueos (Rate Limits) en APIs externas.
    """

    def __init__(self, ttl_seconds: int = 60, max_items: int = 512):
        self.ttl = int(ttl_seconds)
        self.max_items = int(max_items)
        self._lock = threading.Lock()
        self._data: Dict[str, Tuple[float, Any]] = {}  # key -> (expires_at, value)
        
        # Métricas para el Inspector
        self.hits = 0
        self.misses = 0

    def _now(self) -> float:
        return time.time()

    def get(self, key: str, default: Any = None, allow_stale: bool = False) -> Any:
        """Recupera datos. Si falla, el sistema de logs avisará."""
        try:
            with self._lock:
                item = self._data.get(str(key))
                if not item:
                    self.misses += 1
                    return default
                
                expires_at, value = item
                
                # Si permitimos datos viejos (stale) en caso de emergencia
                if allow_stale:
                    self.hits += 1
                    return value
                
                if self._now() <= expires_at:
                    self.hits += 1
                    return value
                
                # Expirado: limpieza inmediata
                self._data.pop(str(key), None)
                self.misses += 1
                return default
        except Exception as e:
            logger.error(f"❌ Error crítico leyendo caché: {e}")
            return default

    def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> None:
        """Guarda datos con validación de integridad."""
        if value is None:
            return

        ttl = self.ttl if ttl_seconds is None else int(ttl_seconds)
        expires_at = self._now() + ttl
        
        try:
            with self._lock:
                # Si el cache está lleno, forzamos limpieza inteligente
                if len(self._data) >= self.max_items:
                    self._evict_some()
                
                self._data[str(key)] = (expires_at, value)
                logger.debug(f"💾 Guardado en caché: {key} (vence en {ttl}s)")
        except Exception as e:
            logger.error(f"❌ Error crítico escribiendo caché: {e}")

    def delete(self, key: str) -> None:
        with self._lock:
            self._data.pop(str(key), None)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()
            self.hits = 0
            self.misses = 0
            logger.info("🧹 Memoria caché vaciada manualmente.")

    def get_stats(self) -> Dict[str, Any]:
        """DIAGNÓSTICO: Devuelve el estado de salud del caché."""
        with self._lock:
            usage_pct = (len(self._data) / self.max_items) * 100
            total_reqs = self.hits + self.misses
            efficiency = (self.hits / total_reqs * 100) if total_reqs > 0 else 0
            
            return {
                "items_count": len(self._data),
                "usage_percent": round(usage_pct, 2),
                "efficiency_percent": round(efficiency, 2),
                "hits": self.hits,
                "misses": self.misses
            }

    def _evict_some(self) -> None:
        """Estrategia de limpieza: LRU (Least Recently Used) simplificado."""
        now = self._now()
        
        # 1. Borrar expirados primero
        expired = [k for k, (exp, _) in self._data.items() if exp < now]
        for k in expired:
            self._data.pop(k, None)
        
        # 2. Si sigue lleno, borrar el 20% que expira más pronto
        if len(self._data) >= self.max_items:
            # Ordenamos por tiempo de expiración
            sorted_items = sorted(self._data.items(), key=lambda kv: kv[1][0])
            num_to_delete = max(1, int(len(sorted_items) * 0.2))
            for i in range(num_to_delete):
                self._data.pop(sorted_items[i][0], None)
            logger.warning(f"⚠️ Caché lleno. Se forzó la eliminación de {num_to_delete} ítems.")
