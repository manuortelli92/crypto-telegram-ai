import os
import math
import time
from typing import Dict, List, Tuple, Optional

import requests
import numpy as np

TIMEFRAME = os.getenv("TIMEFRAME", "1d")
CANDLE_LIMIT = int(os.getenv("CANDLE_LIMIT", "200"))
PRICE_GAP_TOL = float(os.getenv("PRICE_GAP_TOL", "0.02"))  # 2%

BINANCE_KLINES_URL = "https://data-api.binance.vision/api/v3/klines"
KRAKEN_TICKER_URL = "https://api.kraken.com/0/public/Ticker"
COINBASE_TICKER_URL = "https://api.exchange.coinbase.com/products/{product_id}/ticker"
COINGECKO_MARKETS_URL = "https://api.coingecko.com/api/v3/coins/markets"

# name, binance_symbol, kraken_pair, coinbase_product, coingecko_id
UNIVERSE: List[Tuple[str, str, str, str, str]] = [
    ("Bitcoin",  "BTCUSDT", "XBTUSD", "BTC-USD", "bitcoin"),
    ("Ethereum", "ETHUSDT", "ETHUSD", "ETH-USD", "ethereum"),
    ("Solana",   "SOLUSDT", "SOLUSD", "SOL-USD", "solana"),
    ("BNB",      "BNBUSDT", "",       "",       "binancecoin"),
    ("XRP",      "XRPUSDT", "XRPUSD", "XRP-USD", "ripple"),
    ("Cardano",  "ADAUSDT", "ADAUSD", "ADA-USD", "cardano"),
    ("Avalanche","AVAXUSDT","AVAXUSD","AVAX-USD","avalanche-2"),
    ("Chainlink","LINKUSDT","LINKUSD","LINK-USD","chainlink"),
]

def _get(url: str, params=None, timeout: int = 25):
    r = requests.get(url, params=params, timeout=timeout)
    r.raise_for_status()
    return r

def fetch_binance_closes(symbol: str, interval: str, limit: int):
    r = _get(BINANCE_KLINES_URL, params={"symbol": symbol, "interval": interval, "limit": limit})
    data = r.json()
    closes = [float(k[4]) for k in data]
    last_close = float(data[-1][4]) if data else None
    return closes, last_close

def fetch_kraken_price(pair: str) -> Optional[float]:
    if not pair:
        return None
    r = _get(KRAKEN_TICKER_URL, params={"pair": pair})
    j = r.json()
    result = j.get("result") or {}
    if not result:
        return None
    key = list(result.keys())[0]
    last = result[key].get("c", [None])[0]
    return float(last) if last else None

def fetch_coinbase_price(product_id: str) -> Optional[float]:
    if not product_id:
        return None
    r = _get(COINBASE_TICKER_URL.format(product_id=product_id))
    j = r.json()
    p = j.get("price")
    return float(p) if p else None

def fetch_coingecko_markets(ids: List[str]) -> Dict[str, Dict]:
    r = _get(
        COINGECKO_MARKETS_URL,
        params={"vs_currency": "usd", "ids": ",".join(ids), "per_page": 250, "page": 1},
    )
    lst = r.json()
    return {m["id"]: m for m in lst}

def pct_change(a: float, b: float) -> float:
    if a == 0:
        return 0.0
    return (b - a) / a

def features_from_closes(closes: List[float]) -> Dict[str, float]:
    if len(closes) < 35:
        return {"mom_7d": 0.0, "mom_30d": 0.0, "vol_30d": 0.0, "dd_30d": 0.0}

    c = np.array(closes, dtype=float)
    last = c[-1]
    mom_7d = pct_change(c[-8], last)
    mom_30d = pct_change(c[-31], last)

    rets = np.diff(np.log(c[-31:]))
    vol_30d = float(np.std(rets) * np.sqrt(365))

    peak = np.maximum.accumulate(c[-31:])
    dd = (c[-31:] - peak) / peak
    dd_30d = float(dd.min())

    return {"mom_7d": float(mom_7d), "mom_30d": float(mom_30d), "vol_30d": float(vol_30d), "dd_30d": float(dd_30d)}

def within_tol(a: float, b: float, tol: float) -> bool:
    if a is None or b is None or a == 0:
        return False
    return abs(a - b) / a <= tol

def score_asset(feat: Dict[str, float], liquidity_usd: Optional[float], verified_sources: int) -> Dict[str, object]:
    mom_7d = feat["mom_7d"]
    mom_30d = feat["mom_30d"]
    vol = feat["vol_30d"]
    dd = feat["dd_30d"]

    s = 50.0
    s += 25.0 * math.tanh(3.0 * mom_30d)
    s += 10.0 * math.tanh(5.0 * mom_7d)
    s -= 10.0 * math.tanh(2.0 * vol)
    s -= 12.0 * math.tanh(5.0 * abs(dd))

    if liquidity_usd is None:
        s -= 6.0
    else:
        if liquidity_usd < 10_000_000:
            s -= 12.0
        elif liquidity_usd < 50_000_000:
            s -= 6.0
        elif liquidity_usd > 200_000_000:
            s += 6.0

    if verified_sources >= 3:
        s += 6.0
    elif verified_sources == 2:
        s += 2.0
    else:
        s -= 18.0

    s = float(max(0.0, min(100.0, s)))

    risk = "LOW"
    if vol > 0.9 or (liquidity_usd is not None and liquidity_usd < 10_000_000):
        risk = "HIGH"
    elif vol > 0.6 or abs(dd) > 0.20:
        risk = "MEDIUM"

    confidence = min(100, int(verified_sources * 33))
    return {"score": s, "risk": risk, "confidence": confidence}

def fmt_pct(x: float) -> str:
    return f"{x * 100:.2f}%"

def get_ranked_market(prefs: Dict) -> Dict:
    ids = [cg for _, _, _, _, cg in UNIVERSE]
    cg_map = fetch_coingecko_markets(ids)

    avoid = set(prefs.get("avoid") or [])
    focus = set(prefs.get("focus") or [])
    max_picks = int(prefs.get("max_picks") or 3)

    rows = []
    for name, bsymbol, kr_pair, cb_prod, cg_id in UNIVERSE:
        sym = bsymbol.replace("USDT", "")
        if sym in avoid:
            continue
        if focus and sym not in focus:
            continue

        cg = cg_map.get(cg_id, {})
        cg_price = cg.get("current_price")
        cg_vol = cg.get("total_volume")

        closes = []
        bn_last = None
        candles_ok = True
        try:
            closes, bn_last = fetch_binance_closes(bsymbol, TIMEFRAME, CANDLE_LIMIT)
        except Exception:
            candles_ok = False

        kr_last = None
        cb_last = None
        try:
            kr_last = fetch_kraken_price(kr_pair)
        except Exception:
            pass
        try:
            cb_last = fetch_coinbase_price(cb_prod)
        except Exception:
            pass

        anchor = bn_last if bn_last is not None else (float(cg_price) if cg_price else None)
        sources = [
            ("binance", bn_last),
            ("kraken", kr_last),
            ("coinbase", cb_last),
            ("coingecko", float(cg_price) if cg_price else None),
        ]

        verified_sources = 0
        used_sources = []
        if anchor is not None:
            for label, px in sources:
                if px is None:
                    continue
                if within_tol(anchor, px, PRICE_GAP_TOL):
                    verified_sources += 1
                    used_sources.append(label)

        feat = features_from_closes(closes) if (candles_ok and closes) else {"mom_7d": 0.0, "mom_30d": 0.0, "vol_30d": 0.0, "dd_30d": 0.0}
        scored = score_asset(feat, liquidity_usd=cg_vol, verified_sources=verified_sources)

        rows.append({
            "name": name,
            "symbol": sym,
            "pair": bsymbol,
            "score": float(scored["score"]),
            "risk": str(scored["risk"]),
            "confidence": int(scored["confidence"]),
            "mom_7d": float(feat["mom_7d"]),
            "mom_30d": float(feat["mom_30d"]),
            "sources_ok": verified_sources,
            "sources_used": used_sources,
        })

    rows.sort(key=lambda x: x["score"], reverse=True)

    return {
        "generated_utc": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
        "rows": rows,
        "top": rows[:max_picks],
        "tol": PRICE_GAP_TOL,
        "timeframe": TIMEFRAME,
    }