import time
import requests
from typing import Dict, List, Tuple, Optional

COINGECKO_MARKETS = "https://api.coingecko.com/api/v3/coins/markets"

BINANCE_TICKER = "https://api.binance.com/api/v3/ticker/price"
COINBASE_TICKER = "https://api.exchange.coinbase.com/products/{product_id}/ticker"
KRAKEN_TICKER = "https://api.kraken.com/0/public/Ticker"

DEFAULT_TIMEOUT = 20
HEADERS = {"User-Agent": "OrtelliCryptoAI/1.0"}

# TTLs (segundos). Subilos si querés menos requests aún.
TTL_COINGECKO = 180
TTL_BINANCE = 60
TTL_COINBASE = 60
TTL_KRAKEN = 60


def _now() -> float:
    return time.time()


def _cache_get(cache: dict, key: str, ttl: int):
    now = _now()
    item = cache.get(key)
    if not item:
        return None
    ts, val = item
    if now - ts < ttl:
        return val
    return None


def _cache_set(cache: dict, key: str, val):
    cache[key] = (_now(), val)


def _get_json(url: str, params=None, headers=None, timeout: int = DEFAULT_TIMEOUT):
    headers = headers or HEADERS
    r = requests.get(url, params=params, headers=headers, timeout=timeout)
    r.raise_for_status()
    return r.json()


# -------------------------
# CACHES POR FUENTE
# -------------------------
_COINGECKO_CACHE: Dict[str, tuple] = {}
_BINANCE_CACHE: Dict[str, tuple] = {}
_COINBASE_CACHE: Dict[str, tuple] = {}
_KRAKEN_CACHE: Dict[str, tuple] = {}


# -------------------------
# COINGECKO (Top 100)
# -------------------------
def fetch_coingecko_top100(vs: str = "usd") -> List[dict]:
    """
    Devuelve top 100 por market cap desde CoinGecko.
    Cachea para evitar 429.
    Si CoinGecko falla y hay cache, devuelve cache.
    """
    key = f"top100:{vs}"
    cached = _cache_get(_COINGECKO_CACHE, key, TTL_COINGECKO)
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

    try:
        data = _get_json(COINGECKO_MARKETS, params=params)
    except Exception:
        # fallback si rate limit / caída
        if (key in _COINGECKO_CACHE) and (_COINGECKO_CACHE[key][1] is not None):
            return _COINGECKO_CACHE[key][1]
        raise

    rows = []
    for idx, coin in enumerate(data, start=1):
        rows.append({
            "rank": idx,
            "id": coin.get("id"),
            "symbol": (coin.get("symbol") or "").upper().strip(),
            "name": (coin.get("name") or "").strip(),
            "price": float(coin.get("current_price", 0) or 0),
            "market_cap": float(coin.get("market_cap", 0) or 0),
            "volume_24h": float(coin.get("total_volume", 0) or 0),
            "mom_7d": float(coin.get("price_change_percentage_7d_in_currency", 0) or 0),
            "mom_30d": float(coin.get("price_change_percentage_30d_in_currency", 0) or 0),
        })

    _cache_set(_COINGECKO_CACHE, key, rows)
    return rows


# -------------------------
# BINANCE (Ticker price)
# -------------------------
def binance_prices_usdt() -> Dict[str, float]:
    """
    Devuelve dict {"BTCUSDT": 67000.0, ...}
    Binance puede devolver 451 (bloqueo por región/IP).
    Cachea y si falla devuelve {} sin romper nada.
    """
    key = "ticker:usdt"
    cached = _cache_get(_BINANCE_CACHE, key, TTL_BINANCE)
    if cached is not None:
        return cached

    try:
        data = _get_json(BINANCE_TICKER)
    except Exception:
        # fallback: si hay cache viejo, devolvelo; si no, {}
        old = _BINANCE_CACHE.get(key)
        if old and old[1] is not None:
            return old[1]
        return {}

    out: Dict[str, float] = {}
    for it in data:
        sym = it.get("symbol")
        price = it.get("price")
        if sym and price:
            try:
                out[sym] = float(price)
            except Exception:
                pass

    _cache_set(_BINANCE_CACHE, key, out)
    return out


# -------------------------
# COINBASE (Ticker por símbolo)
# -------------------------
def coinbase_price_usd(symbol: str) -> Optional[float]:
    """
    Coinbase spot ticker para SYMBOL-USD.
    Cachea por símbolo para evitar rate limits.
    """
    symbol = (symbol or "").upper().strip()
    if not symbol:
        return None

    key = f"{symbol}-USD"
    cached = _cache_get(_COINBASE_CACHE, key, TTL_COINBASE)
    if cached is not None:
        return cached

    url = COINBASE_TICKER.format(product_id=key)
    try:
        data = _get_json(url)
        p = data.get("price")
        val = float(p) if p is not None else None
        _cache_set(_COINBASE_CACHE, key, val)
        return val
    except Exception:
        # fallback a cache viejo si existía
        old = _COINBASE_CACHE.get(key)
        if old and old[1] is not None:
            return old[1]
        return None


# -------------------------
# KRAKEN (Ticker por símbolo)
# -------------------------
def kraken_price_usd(symbol: str) -> Optional[float]:
    """
    Kraken ticker: intentamos varias variantes.
    Cachea por símbolo.
    """
    symbol = (symbol or "").upper().strip()
    if not symbol:
        return None

    key = f"{symbol}-USD"
    cached = _cache_get(_KRAKEN_CACHE, key, TTL_KRAKEN)
    if cached is not None:
        return cached

    pairs_try = [f"{symbol}USD"]

    if symbol == "BTC":
        pairs_try += ["XXBTZUSD", "XBTUSD"]
    if symbol == "ETH":
        pairs_try += ["XETHZUSD", "ETHUSD"]
    if symbol == "SOL":
        pairs_try += ["SOLUSD"]
    if symbol == "XRP":
        pairs_try += ["XRPUSD"]
    if symbol == "ADA":
        pairs_try += ["ADAUSD"]
    if symbol == "DOGE":
        pairs_try += ["DOGEUSD"]
    if symbol == "BNB":
        pairs_try += ["BNBUSD"]

    for pair in pairs_try:
        try:
            data = _get_json(KRAKEN_TICKER, params={"pair": pair})
            result = data.get("result") or {}
            if not result:
                continue
            k = next(iter(result.keys()))
            ticker = result[k]
            c = ticker.get("c")
            if c and len(c) > 0:
                val = float(c[0])
                _cache_set(_KRAKEN_CACHE, key, val)
                return val
        except Exception:
            continue

    # fallback a cache viejo si existía
    old = _KRAKEN_CACHE.get(key)
    if old and old[1] is not None:
        return old[1]
    return None


# -------------------------
# Utils
# -------------------------
def median(values: List[float]) -> Optional[float]:
    vs = sorted([v for v in values if v is not None])
    if not vs:
        return None
    n = len(vs)
    mid = n // 2
    if n % 2 == 1:
        return vs[mid]
    return (vs[mid - 1] + vs[mid]) / 2.0


# -------------------------
# Verificación Multi-fuente
# -------------------------
def verify_prices(
    rows: List[dict],
    verify_threshold_pct: float = 2.0,
) -> Tuple[List[dict], dict]:
    """
    Enriquecemos cada row con:
      - sources: precios por fuente
      - price_anchor: mediana de fuentes disponibles
      - spread_pct: (max-min)/anchor*100
      - sources_ok: fuentes dentro del umbral vs anchor
      - verified: sources_ok >= 2

    stats global:
      - verified_pct
      - avg_spread_pct
      - median_spread_pct
    """
    bn = binance_prices_usdt()

    enriched: List[dict] = []
    spreads: List[float] = []
    verified_count = 0
    total = 0

    for r in rows:
        sym = r.get("symbol")
        if not sym:
            continue

        sources: Dict[str, float] = {}

        # Binance USDT (si está disponible)
        bkey = f"{sym}USDT"
        if bkey in bn:
            sources["binance"] = bn[bkey]

        # Coinbase USD (cacheado)
        cb = coinbase_price_usd(sym)
        if cb is not None:
            sources["coinbase"] = cb

        # Kraken USD (cacheado)
        kk = kraken_price_usd(sym)
        if kk is not None:
            sources["kraken"] = kk

        # CoinGecko (ya viene en r["price"]) también cuenta como fuente
        cg_price = r.get("price")
        if cg_price is not None and float(cg_price) > 0:
            sources["coingecko"] = float(cg_price)

        prices = list(sources.values())
        anchor = median(prices)

        spread_pct = None
        sources_ok = 0
        verified = False

        if anchor is not None and anchor > 0 and prices:
            mx = max(prices)
            mn = min(prices)
            spread_pct = ((mx - mn) / anchor) * 100.0

            for p in prices:
                gap = abs(p - anchor) / anchor * 100.0
                if gap <= verify_threshold_pct:
                    sources_ok += 1

            verified = sources_ok >= 2
            spreads.append(float(spread_pct))

        rr = dict(r)
        rr["sources"] = sources
        rr["price_anchor"] = float(anchor) if anchor is not None else None
        rr["spread_pct"] = float(spread_pct) if spread_pct is not None else None
        rr["sources_ok"] = int(sources_ok)
        rr["verified"] = bool(verified)

        enriched.append(rr)

        total += 1
        if verified:
            verified_count += 1

    stats = {
        "total": total,
        "verified": verified_count,
        "verified_pct": (verified_count / total * 100.0) if total else 0.0,
        "avg_spread_pct": (sum(spreads) / len(spreads)) if spreads else None,
        "median_spread_pct": median(spreads) if spreads else None,
    }

    return enriched, stats