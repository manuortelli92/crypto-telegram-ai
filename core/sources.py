import time
import requests
from typing import Dict, Optional, Tuple

from core.cache import TTLCache

_cache = TTLCache(default_ttl_sec=300)

COINGECKO_MARKETS = "https://api.coingecko.com/api/v3/coins/markets"
COINBASE_SPOT = "https://api.coinbase.com/v2/prices/{product}-spot"
KRAKEN_TICKER = "https://api.kraken.com/0/public/Ticker"

_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": "OrtelliCryptoBot/1.0"})


def _get_json(url: str, params: Optional[dict] = None, timeout: int = 20) -> dict:
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

    # Backoff muy simple para 429
    for wait in (0, 2, 5):
        if wait:
            time.sleep(wait)
        try:
            data = _get_json(COINGECKO_MARKETS, params=params, timeout=25)
            _cache.set(key, data, ttl_sec=300)  # 5 min
            return data
        except requests.HTTPError as e:
            status = getattr(e.response, "status_code", None)
            if status == 429:
                continue
            raise

    # Si sigue 429, devolvemos lo último que haya (si había) o re-lanzamos
    cached = _cache.get(key)
    if cached is not None:
        return cached
    raise RuntimeError("CoinGecko rate-limited (429). Probá en 1-2 minutos.")


def _kraken_pair(symbol: str) -> Optional[str]:
    # Kraken usa XBT para BTC, y pares contra USD suelen existir para majors.
    s = symbol.upper()
    if s == "BTC":
        s = "XBT"
    # Algunos en Kraken son USD, otros USDT; probamos USD primero.
    return f"{s}USD"


def kraken_spot_price_usd(symbol: str) -> Optional[float]:
    key = f"kraken:spot:{symbol}"
    cached = _cache.get(key)
    if cached is not None:
        return cached

    pair = _kraken_pair(symbol)
    if not pair:
        return None

    try:
        data = _get_json(KRAKEN_TICKER, params={"pair": pair}, timeout=15)
        result = data.get("result") or {}
        if not result:
            return None
        # La key real a veces es distinta, tomamos la primera
        first = next(iter(result.values()))
        last = float(first["c"][0])
        _cache.set(key, last, ttl_sec=120)
        return last
    except Exception:
        return None


def _coinbase_product(symbol: str) -> Optional[str]:
    # Coinbase usa formato BTC-USD, ETH-USD...
    s = symbol.upper()
    return f"{s}-USD"


def coinbase_spot_price_usd(symbol: str) -> Optional[float]:
    key = f"coinbase:spot:{symbol}"
    cached = _cache.get(key)
    if cached is not None:
        return cached

    product = _coinbase_product(symbol)
    if not product:
        return None

    try:
        url = COINBASE_SPOT.format(product=product)
        data = _get_json(url, timeout=15)
        amount = float(data["data"]["amount"])
        _cache.set(key, amount, ttl_sec=120)
        return amount
    except Exception:
        return None


def verify_price_multi_source(anchor_price: float, symbol: str, tolerance_pct: float = 2.0) -> Tuple[int, str]:
    """
    Devuelve:
      - sources_ok: cuántas fuentes caen dentro del tolerance_pct vs anchor
      - used: string con fuentes usadas
    """
    used = []
    ok = 0

    def within(p: float) -> bool:
        if not p or anchor_price <= 0:
            return False
        gap = abs(p - anchor_price) / anchor_price * 100.0
        return gap <= tolerance_pct

    # Kraken
    pk = kraken_spot_price_usd(symbol)
    if pk is not None:
        used.append("kraken")
        if within(pk):
            ok += 1

    # Coinbase
    pc = coinbase_spot_price_usd(symbol)
    if pc is not None:
        used.append("coinbase")
        if within(pc):
            ok += 1

    # CoinGecko es anchor, pero lo contamos como fuente usada para claridad
    used.insert(0, "coingecko")
    return ok, ", ".join(used)