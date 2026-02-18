import time
import requests
import logging
import os
from typing import Dict, List, Tuple, Optional

logger = logging.getLogger(__name__)

# Configuración de URLs
COINGECKO_MARKETS = "https://api.coingecko.com/api/v3/coins/markets"
BINANCE_TICKER = "https://api.binance.com/api/v3/ticker/price"
COINBASE_TICKER = "https://api.exchange.coinbase.com/products/{product_id}/ticker"
KRAKEN_TICKER = "https://api.kraken.com/0/public/Ticker"

DEFAULT_TIMEOUT = 25
HEADERS = {"User-Agent": "OrtelliCryptoAI/1.0"}

# TTLs (Tiempo de vida en cache) - Optimizados para Railway
TTL_COINGECKO = 300  # 5 min (evita el 429 agresivo)
TTL_BINANCE = 60
TTL_COINBASE = 60
TTL_KRAKEN = 60

# Caches globales en memoria
_CACHES: Dict[str, Dict[str, tuple]] = {
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
        _CACHES[source][key] = (_now(), val)

def _get_json(url: str, params=None, headers=None, timeout: int = DEFAULT_TIMEOUT):
    headers = headers or HEADERS
    try:
        r = requests.get(url, params=params, headers=headers, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.debug(f"Error en request a {url}: {e}")
        raise

# --- COINGECKO ---
def fetch_coingecko_top100(vs: str = "usd") -> List[dict]:
    key = f"top100:{vs}"
    cached = _cache_get("coingecko", key, TTL_COINGECKO)
    if cached: return cached

    params = {
        "vs_currency": vs, "order": "market_cap_desc",
        "per_page": 100, "page": 1, "sparkline": False,
        "price_change_percentage": "7d,30d",
    }

    try:
        data = _get_json(COINGECKO_MARKETS, params=params)
        rows = []
        for idx, coin in enumerate(data, start=1):
            rows.append({
                "rank": idx,
                "id": coin.get("id"),
                "symbol": (coin.get("symbol") or "").upper().strip(),
                "name": (coin.get("name") or "").strip(),
                "price": float(coin.get("current_price") or 0),
                "market_cap": float(coin.get("market_cap") or 0),
                "volume_24h": float(coin.get("total_volume") or 0),
                "mom_7d": float(coin.get("price_change_percentage_7d_in_currency") or 0),
                "mom_30d": float(coin.get("price_change_percentage_30d_in_currency") or 0),
            })
        _cache_set("coingecko", key, rows)
        return rows
    except Exception:
        # Fallback a cache expirado
        old = _CACHES["coingecko"].get(key)
        return old[1] if old else []

# --- BINANCE ---
def binance_prices_usdt() -> Dict[str, float]:
    key = "ticker:usdt"
    cached = _cache_get("binance", key, TTL_BINANCE)
    if cached: return cached

    try:
        data = _get_json(BINANCE_TICKER)
        out = {it["symbol"]: float(it["price"]) for it in data if "symbol" in it and "price" in it}
        _cache_set("binance", key, out)
        return out
    except Exception:
        old = _CACHES["binance"].get(key)
        return old[1] if old else {}

# --- COINBASE ---
def coinbase_price_usd(symbol: str) -> Optional[float]:
    key = f"{symbol.upper()}-USD"
    cached = _cache_get("coinbase", key, TTL_COINBASE)
    if cached: return cached

    try:
        url = COINBASE_TICKER.format(product_id=key)
        data = _get_json(url)
        price = float(data.get("price") or 0)
        _cache_set("coinbase", key, price)
        return price
    except Exception:
        old = _CACHES["coinbase"].get(key)
        return old[1] if old else None

# --- VERIFICACIÓN MULTI-FUENTE ---
def median(values: List[float]) -> Optional[float]:
    vs = sorted([v for v in values if v > 0])
    if not vs: return None
    n = len(vs)
    mid = n // 2
    return vs[mid] if n % 2 == 1 else (vs[mid - 1] + vs[mid]) / 2.0

def verify_prices(rows: List[dict], threshold: float = 2.0) -> Tuple[List[dict], dict]:
    """Cruza los datos de CoinGecko con otros exchanges para validar el precio."""
    bn = binance_prices_usdt()
    enriched = []
    spreads = []
    verified_count = 0

    for r in rows:
        sym = r.get("symbol")
        if not sym: continue

        # Recolectar precios de fuentes
        sources = {"coingecko": r["price"]}
        
        # Binance
        if f"{sym}USDT" in bn: sources["binance"] = bn[f"{sym}USDT"]
        
        # Coinbase (solo top 20 para no saturar)
        if r["rank"] <= 20:
            cb = coinbase_price_usd(sym)
            if cb: sources["coinbase"] = cb

        prices = list(sources.values())
        anchor = median(prices)
        
        verified = False
        spread_pct = 0.0
        
        if anchor and anchor > 0:
            spread_pct = ((max(prices) - min(prices)) / anchor) * 100.0
            # Es verificado si al menos 2 fuentes coinciden (dentro del threshold)
            matches = sum(1 for p in prices if (abs(p - anchor) / anchor * 100.0) <= threshold)
            verified = matches >= 2
            spreads.append(spread_pct)

        rr = {**r, "price_anchor": anchor, "spread_pct": spread_pct, "verified": verified, "sources_count": len(sources)}
        enriched.append(rr)
        if verified: verified_count += 1

    stats = {
        "total": len(enriched),
        "verified": verified_count,
        "verified_pct": (verified_count / len(enriched) * 100) if enriched else 0,
        "avg_spread": (sum(spreads) / len(spreads)) if spreads else 0
    }
    return enriched, stats
