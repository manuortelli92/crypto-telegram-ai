import time
import requests
import logging
import os
from typing import Dict, List, Tuple, Optional, Any

# Configuración de Logging con formato de diagnóstico
logger = logging.getLogger(__name__)

# Configuración de URLs
COINGECKO_MARKETS = "https://api.coingecko.com/api/v3/coins/markets"
BINANCE_TICKER = "https://api.binance.com/api/v3/ticker/price"
COINBASE_TICKER = "https://api.exchange.coinbase.com/products/{product_id}/ticker"

DEFAULT_TIMEOUT = 15  # Reducido para evitar que el bot se cuelgue
HEADERS = {"User-Agent": "OrtelliCryptoAI/1.0", "Accept": "application/json"}

# Tiempos de Cache (TTLs)
TTL_COINGECKO = 300  # 5 minutos para evitar baneos
TTL_BINANCE = 60     # 1 minuto
TTL_COINBASE = 60

# Almacenamiento persistente en memoria durante la ejecución
_CACHES: Dict[str, Dict[str, Tuple[float, Any]]] = {
    "coingecko": {}, "binance": {}, "coinbase": {}, "kraken": {}
}

def _now() -> float:
    return time.time()

def _cache_get(source: str, key: str, ttl: int):
    item = _CACHES.get(source, {}).get(key)
    if not item: return None
    ts, val = item
    if _now() - ts < ttl:
        return val
    return None

def _cache_set(source: str, key: str, val):
    if val is not None:
        if source not in _CACHES: _CACHES[source] = {}
        _CACHES[source][key] = (_now(), val)

def _get_json(url: str, params=None, headers=None, timeout: int = DEFAULT_TIMEOUT):
    """Encapsulador de requests con manejo de errores inteligente."""
    actual_headers = HEADERS.copy()
    if headers: actual_headers.update(headers)
    
    # Soporte para API Key de CoinGecko si existe en Railway
    cg_key = os.getenv("COINGECKO_API_KEY")
    if "coingecko" in url and cg_key:
        actual_headers["x-cg-demo-api-key"] = cg_key

    try:
        r = requests.get(url, params=params, headers=actual_headers, timeout=timeout)
        if r.status_code == 429:
            logger.warning(f"⚠️ Rate Limit (429) detectado en {url}. Usando cache.")
            return None
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.error(f"❌ Error en request a {url[:40]}: {e}")
        return None

# --- COINGECKO ---
def fetch_coingecko_top100(vs: str = "usd") -> List[dict]:
    key = f"top100:{vs}"
    cached = _cache_get("coingecko", key, TTL_COINGECKO)
    if cached: return cached

    params = {
        "vs_currency": vs, "order": "market_cap_desc",
        "per_page": 100, "page": 1, "sparkline": False,
        "price_change_percentage": "24h,7d,30d",
    }

    data = _get_json(COINGECKO_MARKETS, params=params)
    
    if data:
        rows = []
        for idx, coin in enumerate(data, start=1):
            rows.append({
                "rank": coin.get("market_cap_rank") or idx,
                "id": coin.get("id"),
                "symbol": (coin.get("symbol") or "").upper().strip(),
                "name": (coin.get("name") or "").strip(),
                "current_price": float(coin.get("current_price") or 0),
                "market_cap": float(coin.get("market_cap") or 0),
                "volume_24h": float(coin.get("total_volume") or 0),
                "price_change_percentage_24h": float(coin.get("price_change_percentage_24h") or 0),
                "mom_7d": float(coin.get("price_change_percentage_7d_in_currency") or 0),
                "mom_30d": float(coin.get("price_change_percentage_30d_in_currency") or 0),
            })
        _cache_set("coingecko", key, rows)
        return rows
    
    # Fallback agresivo: si la API falla, devolver lo último que tengamos
    old = _CACHES["coingecko"].get(key)
    return old[1] if old else []

# --- BINANCE ---
def binance_prices_usdt() -> Dict[str, float]:
    key = "ticker:usdt"
    cached = _cache_get("binance", key, TTL_BINANCE)
    if cached: return cached

    data = _get_json(BINANCE_TICKER)
    if data and isinstance(data, list):
        out = {it["symbol"]: float(it["price"]) for it in data if "symbol" in it and "price" in it}
        _cache_set("binance", key, out)
        return out
    
    old = _CACHES["binance"].get(key)
    return old[1] if old else {}

# --- VERIFICACIÓN MULTI-FUENTE ---
def median(values: List[float]) -> Optional[float]:
    vs = sorted([v for v in values if v > 0])
    if not vs: return None
    n = len(vs)
    mid = n // 2
    return vs[mid] if n % 2 == 1 else (vs[mid - 1] + vs[mid]) / 2.0

def verify_price_multi_source(price: float, symbol: str) -> Tuple[int, str]:
    """
    Función requerida por el Engine para validar un precio específico.
    """
    bn = binance_prices_usdt()
    sources_count = 1 # Ya tenemos CoinGecko
    ticker = f"{symbol.upper()}USDT"
    
    if ticker in bn:
        binance_p = bn[ticker]
        diff = abs(price - binance_p) / price
        if diff < 0.05: # Menos del 5% de diferencia
            sources_count += 1
            
    return sources_count, "OK"
