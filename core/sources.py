import time
import requests
import logging
from typing import Dict, Optional, Tuple, List
from core.cache import TTLCache

logger = logging.getLogger(__name__)

# Cache de 5 minutos para el Top 100 y 1 minuto para precios específicos
_cache = TTLCache(ttl_seconds=300, max_items=1024)

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

    # Reintentos con espera progresiva para evitar el error 429
    for wait in (0, 3, 7):
        if wait:
            time.sleep(wait)
        try:
            data = _get_json(COINGECKO_MARKETS, params=params, timeout=25)
            # Guardamos los datos puros en el cache
            _cache.set(key, data)
            return data
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:
                logger.warning("CoinGecko rate-limit (429). Reintentando...")
                continue
            raise
        except Exception as e:
            logger.error(f"Error en fetch_coingecko: {e}")
            break

    # Si fallaron los reintentos, devolvemos lo que tengamos (aunque esté vencido)
    return _cache.get(key, allow_stale=True) or []

def kraken_spot_price_usd(symbol: str) -> Optional[float]:
    sym = symbol.upper()
    if sym == "BTC": sym = "XBT"
    pair = f"{sym}USD"
    
    key = f"kraken:spot:{sym}"
    cached = _cache.get(key)
    if cached: return cached

    try:
        data = _get_json(KRAKEN_TICKER, params={"pair": pair}, timeout=15)
        result = data.get("result", {})
        if not result: return None
        first_key = next(iter(result))
        price = float(result[first_key]["c"][0])
        _cache.set(key, price, ttl_seconds=60) # Precio spot dura 1 min
        return price
    except Exception:
        return None

def coinbase_spot_price_usd(symbol: str) -> Optional[float]:
    sym = symbol.upper()
    key = f"coinbase:spot:{sym}"
    cached = _cache.get(key)
    if cached: return cached

    try:
        url = COINBASE_SPOT.format(product=f"{sym}-USD")
        data = _get_json(url, timeout=15)
        price = float(data["data"]["amount"])
        _cache.set(key, price, ttl_seconds=60)
        return price
    except Exception:
        return None

def verify_price_multi_source(anchor_price: float, symbol: str, tolerance_pct: float = 2.0) -> Tuple[int, str]:
    """
    Compara el precio base contra Kraken y Coinbase.
    Retorna cantidad de fuentes que coinciden y cuáles se usaron.
    """
    used = ["coingecko"]
    ok_count = 1 # CoinGecko es el punto de partida

    def is_near(p: float) -> bool:
        return abs(p - anchor_price) / anchor_price * 100.0 <= tolerance_pct

    # Chequeo Kraken
    pk = kraken_spot_price_usd(symbol)
    if pk:
        used.append("kraken")
        if is_near(pk): ok_count += 1

    # Chequeo Coinbase
    pc = coinbase_spot_price_usd(symbol)
    if pc:
        used.append("coinbase")
        if is_near(pc): ok_count += 1

    return ok_count, ", ".join(used)
