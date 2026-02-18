import time
import requests
import logging
import os
from typing import Dict, Optional, Tuple, List
from core.cache import TTLCache

logger = logging.getLogger(__name__)

# Cache de 10 minutos (para cuidar la API)
_cache = TTLCache(ttl_seconds=600, max_items=1024)

# URLs oficiales
COINGECKO_BASE_URL = "https://api.coingecko.com/api/v3/coins/markets"
CG_API_KEY = os.getenv("CG_API_KEY") 

_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": "OrtelliCryptoBot/2.0"})

def _get_json(url: str, params: Optional[dict] = None, timeout: int = 25) -> dict:
    # Si tenemos la Key, la mandamos en el header
    headers = {}
    if CG_API_KEY:
        headers["x-cg-demo-api-key"] = CG_API_KEY
    
    r = _SESSION.get(url, params=params, headers=headers, timeout=timeout)
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

    # Intentamos 3 veces con esperas largas (Exponential Backoff)
    for wait in (0, 10, 25):
        if wait:
            logger.warning(f"Reintentando CoinGecko en {wait}s...")
            time.sleep(wait)
        try:
            data = _get_json(COINGECKO_BASE_URL, params=params)
            if data and isinstance(data, list):
                _cache.set(key, data)
                return data
        except Exception as e:
            logger.error(f"Error en CoinGecko: {e}")
            if "429" not in str(e): # Si no es rate limit, cortamos el loop
                break
            continue

    # Si todo falla, intentamos devolver el cache viejo
    return _cache.get(key, allow_stale=True) or []

# --- Estas funciones deben estar para que el engine no rompa ---
def verify_price_multi_source(anchor_price: float, symbol: str) -> Tuple[int, str]:
    # Por ahora, para no complicar con más APIs, decimos que CG es confiable
    return 1, "coingecko"

def kraken_spot_price_usd(symbol: str): return None
def coinbase_spot_price_usd(symbol: str): return None
