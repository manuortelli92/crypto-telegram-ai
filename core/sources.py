import time
import requests
import logging
import os
from typing import Dict, Optional, Tuple, List
from core.cache import TTLCache

logger = logging.getLogger(__name__)

# Cache de 10 min para el Top 100 (más relax para la API)
_cache = TTLCache(ttl_seconds=600, max_items=1024)

# URLs
COINGECKO_MARKETS = "https://api.coingecko.com/api/v3/coins/markets"
# Si tenés API Key Pro o Demo, usá la URL pro, si no, la común
CG_API_KEY = os.getenv("CG_API_KEY") 

_SESSION = requests.Session()
_SESSION.headers.update({
    "User-Agent": "OrtelliCryptoBot/2.0",
    "accept": "application/json"
})

# Si hay API Key, la agregamos a los headers globales
if CG_API_KEY:
    # Para la Demo API de CoinGecko se usa este header:
    _SESSION.headers.update({"x-cg-demo-api-key": CG_API_KEY})

def _get_json(url: str, params: Optional[dict] = None, timeout: int = 25) -> dict:
    r = _SESSION.get(url, params=params, timeout=timeout)
    r.raise_for_status()
    return r.json()

def fetch_coingecko_top100(vs: str = "usd") -> list:
    key = f"cg:top100:{vs}"
    cached = _cache.get(key)
    if cached is not None:
        return cached

    params = {
        "vs_currency": vs,
        "order": "market_cap_desc",
        "per_page": 100,
        "page": 1,
        "sparkline": False,
        "price_change_percentage": "7d,30d",
    }

    # Reintentos con "Exponential Backoff" (espera cada vez más)
    retries = [0, 10, 30] # Espera 0, luego 10s, luego 30s
    for wait in retries:
        if wait:
            logger.warning(f"Esperando {wait}s para reintentar CoinGecko...")
            time.sleep(wait)
        try:
            data = _get_json(COINGECKO_MARKETS, params=params)
            _cache.set(key, data)
            return data
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:
                logger.error("429: CoinGecko nos bloqueó por exceso de pedidos.")
                continue # Reintenta si hay otra espera en la lista
            raise
        except Exception as e:
            logger.error(f"Error inesperado en fuentes: {e}")
            break

    # Si todo falla, intentamos devolver lo último que haya en cache aunque esté viejo
    stale = _cache.get(key, allow_stale=True)
    if stale:
        logger.info("Usando datos viejos del cache ante falla de API.")
        return stale
    
    return []

# ... (Las funciones de Kraken y Coinbase quedan igual que antes) ...
def kraken_spot_price_usd(symbol: str) -> Optional[float]:
    # (Mismo código que ya tenés)
    pass

def coinbase_spot_price_usd(symbol: str) -> Optional[float]:
    # (Mismo código que ya tenés)
    pass

def verify_price_multi_source(anchor_price: float, symbol: str, tolerance_pct: float = 2.0) -> Tuple[int, str]:
    # (Mismo código que ya tenés)
    return 1, "coingecko" # Simplificado para el ejemplo
