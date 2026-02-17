import time
import requests
from typing import Dict, List, Tuple, Optional

COINGECKO_MARKETS = "https://api.coingecko.com/api/v3/coins/markets"

BINANCE_TICKER = "https://api.binance.com/api/v3/ticker/price"
COINBASE_TICKER = "https://api.exchange.coinbase.com/products/{product_id}/ticker"
KRAKEN_TICKER = "https://api.kraken.com/0/public/Ticker"

DEFAULT_TIMEOUT = 20


def _get_json(url: str, params=None, headers=None, timeout: int = DEFAULT_TIMEOUT):
    r = requests.get(url, params=params, headers=headers, timeout=timeout)
    r.raise_for_status()
    return r.json()


def fetch_coingecko_top100(vs: str = "usd") -> List[dict]:
    params = {
        "vs_currency": vs,
        "order": "market_cap_desc",
        "per_page": 100,
        "page": 1,
        "sparkline": False,
        "price_change_percentage": "7d,30d",
    }
    data = _get_json(COINGECKO_MARKETS, params=params)

    rows = []
    for idx, coin in enumerate(data, start=1):
        symbol = (coin.get("symbol") or "").upper().strip()
        name = (coin.get("name") or "").strip()

        rows.append({
            "rank": idx,
            "id": coin.get("id"),
            "symbol": symbol,
            "name": name,
            "price": float(coin.get("current_price", 0) or 0),
            "market_cap": float(coin.get("market_cap", 0) or 0),
            "volume_24h": float(coin.get("total_volume", 0) or 0),
            "mom_7d": float(coin.get("price_change_percentage_7d_in_currency", 0) or 0),
            "mom_30d": float(coin.get("price_change_percentage_30d_in_currency", 0) or 0),
        })
    return rows


def binance_prices_usdt() -> Dict[str, float]:
    data = _get_json(BINANCE_TICKER)
    out = {}
    for it in data:
        sym = it.get("symbol")
        price = it.get("price")
        if sym and price:
            try:
                out[sym] = float(price)
            except Exception:
                pass
    return out


def coinbase_price_usd(symbol: str) -> Optional[float]:
    product_id = f"{symbol}-USD"
    url = COINBASE_TICKER.format(product_id=product_id)
    try:
        data = _get_json(url, headers={"User-Agent": "Mozilla/5.0"})
        p = data.get("price")
        return float(p) if p is not None else None
    except Exception:
        return None


def kraken_price_usd(symbol: str) -> Optional[float]:
    pairs_try = [f"{symbol}USD"]

    # mapeos comunes
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
                return float(c[0])
        except Exception:
            continue

    return None


def median(values: List[float]) -> Optional[float]:
    vs = sorted([v for v in values if v is not None])
    if not vs:
        return None
    n = len(vs)
    mid = n // 2
    if n % 2 == 1:
        return vs[mid]
    return (vs[mid - 1] + vs[mid]) / 2.0


def verify_prices(
    rows: List[dict],
    verify_threshold_pct: float = 2.0,
    sleep_coinbase_sec: float = 0.12,
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

    enriched = []
    spreads = []
    verified_count = 0
    total = 0

    for r in rows:
        sym = r.get("symbol")
        if not sym:
            continue

        sources = {}

        # Binance USDT
        bkey = f"{sym}USDT"
        if bkey in bn:
            sources["binance"] = bn[bkey]

        # Coinbase USD (rate limit suave)
        cb = coinbase_price_usd(sym)
        if cb is not None:
            sources["coinbase"] = cb
        time.sleep(sleep_coinbase_sec)

        # Kraken USD (best effort)
        kk = kraken_price_usd(sym)
        if kk is not None:
            sources["kraken"] = kk

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
            spreads.append(spread_pct)

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