import os
import time
import math
import logging
from typing import Dict, List, Tuple, Optional

import requests
import numpy as np

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("Missing BOT_TOKEN env var. Set it in Railway > Variables.")

# --- Config ---
TIMEFRAME = os.getenv("TIMEFRAME", "1d")            # used for primary candles
CANDLE_LIMIT = int(os.getenv("CANDLE_LIMIT", "200"))
PRICE_GAP_TOL = float(os.getenv("PRICE_GAP_TOL", "0.02"))  # 2%

# Primary candles source (reliable on cloud):
BINANCE_KLINES_URL = "https://data-api.binance.vision/api/v3/klines"

# Secondary price sources (spot):
KRAKEN_TICKER_URL = "https://api.kraken.com/0/public/Ticker"
COINBASE_TICKER_URL = "https://api.exchange.coinbase.com/products/{product_id}/ticker"
COINGECKO_MARKETS_URL = "https://api.coingecko.com/api/v3/coins/markets"

# Universe with per-exchange symbol mapping:
# name, binance_symbol, kraken_pair, coinbase_product, coingecko_id
UNIVERSE: List[Tuple[str, str, str, str, str]] = [
    ("Bitcoin",  "BTCUSDT", "XBTUSD", "BTC-USD", "bitcoin"),
    ("Ethereum", "ETHUSDT", "ETHUSD", "ETH-USD", "ethereum"),
    ("Solana",   "SOLUSDT", "SOLUSD", "SOL-USD", "solana"),
    ("BNB",      "BNBUSDT", "",       "",       "binancecoin"),  # often not on Kraken/Coinbase
    ("XRP",      "XRPUSDT", "XRPUSD", "XRP-USD", "ripple"),
    ("Cardano",  "ADAUSDT", "ADAUSD", "ADA-USD", "cardano"),
    ("Avalanche","AVAXUSDT","AVAXUSD","AVAX-USD","avalanche-2"),
    ("Chainlink","LINKUSDT","LINKUSD","LINK-USD","chainlink"),
]


# ---------- Data fetch ----------
def fetch_binance_closes(symbol: str, interval: str, limit: int) -> Tuple[List[float], Optional[float]]:
    r = requests.get(
        BINANCE_KLINES_URL,
        params={"symbol": symbol, "interval": interval, "limit": limit},
        timeout=25,
    )
    r.raise_for_status()
    data = r.json()
    closes = [float(k[4]) for k in data]
    last_close = float(data[-1][4]) if data else None
    return closes, last_close


def fetch_kraken_price(pair: str) -> Optional[float]:
    if not pair:
        return None
    r = requests.get(KRAKEN_TICKER_URL, params={"pair": pair}, timeout=25)
    r.raise_for_status()
    j = r.json()
    result = j.get("result") or {}
    if not result:
        return None
    # Kraken returns dynamic key, take first:
    key = list(result.keys())[0]
    last = result[key].get("c", [None])[0]
    return float(last) if last else None


def fetch_coinbase_price(product_id: str) -> Optional[float]:
    if not product_id:
        return None
    url = COINBASE_TICKER_URL.format(product_id=product_id)
    r = requests.get(url, timeout=25)
    r.raise_for_status()
    j = r.json()
    price = j.get("price")
    return float(price) if price else None


def fetch_coingecko_prices(ids: List[str]) -> Dict[str, Dict]:
    r = requests.get(
        COINGECKO_MARKETS_URL,
        params={"vs_currency": "usd", "ids": ",".join(ids), "per_page": 250, "page": 1},
        timeout=25,
    )
    r.raise_for_status()
    lst = r.json()
    return {m["id"]: m for m in lst}


# ---------- Features / scoring ----------
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

    # liquidity (use coingecko total_volume as proxy if available)
    if liquidity_usd is None:
        s -= 6.0
    else:
        if liquidity_usd < 10_000_000:
            s -= 12.0
        elif liquidity_usd < 50_000_000:
            s -= 6.0
        elif liquidity_usd > 200_000_000:
            s += 6.0

    # verification bonus/penalty
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

    # confidence: 0..100
    confidence = min(100, int(verified_sources * 33))

    return {"score": s, "risk": risk, "confidence": confidence}


def fmt_pct(x: float) -> str:
    return f"{x * 100:.2f}%"


def within_tol(a: float, b: float, tol: float) -> bool:
    if a is None or b is None:
        return False
    if a == 0:
        return False
    return abs(a - b) / a <= tol


def build_report(top_n: int = 5) -> str:
    ids = [cg_id for _, _, _, _, cg_id in UNIVERSE]
    cg_map = fetch_coingecko_prices(ids)

    rows = []
    for name, bsymbol, kr_pair, cb_prod, cg_id in UNIVERSE:
        cg = cg_map.get(cg_id, {})
        cg_price = cg.get("current_price")
        cg_vol = cg.get("total_volume")  # liquidity proxy

        # Primary candles + primary last price
        closes = []
        bn_last = None
        candles_ok = True
        try:
            closes, bn_last = fetch_binance_closes(bsymbol, TIMEFRAME, CANDLE_LIMIT)
        except Exception:
            candles_ok = False

        # Secondary sources (last prices)
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

        # Verification: count how many sources agree with primary (bn_last). If bn_last missing, fallback to cg_price.
        anchor = bn_last if bn_last is not None else (float(cg_price) if cg_price else None)

        sources = []
        if anchor is not None:
            sources.append(("binance", bn_last))
            sources.append(("kraken", kr_last))
            sources.append(("coinbase", cb_last))
            sources.append(("coingecko", float(cg_price) if cg_price else None))

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
            "symbol": bsymbol,
            "score": scored["score"],
            "risk": scored["risk"],
            "confidence": scored["confidence"],
            "mom_30d": feat["mom_30d"],
            "mom_7d": feat["mom_7d"],
            "verified_sources": verified_sources,
            "used_sources": used_sources,
            "candles_ok": candles_ok,
        })

    rows.sort(key=lambda x: float(x["score"]), reverse=True)
    top = rows[:top_n]

    # Format: more human-friendly
    lines = []
    lines.append("MARKET BRIEF (multi-source)")
    lines.append(time.strftime("UTC %Y-%m-%d %H:%M:%S", time.gmtime()))
    lines.append("")
    lines.append("TOP PICKS (you decide):")

    for i, r in enumerate(top, 1):
        lines.append(
            f"{i}) {r['name']} ({r['symbol']}) | score {r['score']:.1f} | conf {r['confidence']} | risk {r['risk']}"
        )
        lines.append(
            f"   mom: 7d {fmt_pct(float(r['mom_7d']))} | 30d {fmt_pct(float(r['mom_30d']))}"
        )
        lines.append(
            f"   sources_ok: {r['verified_sources']} | used: {', '.join(r['used_sources']) if r['used_sources'] else 'none'}"
        )

    lines.append("")
    lines.append("NOTES:")
    lines.append(f"- verified_sources counts sources within {int(PRICE_GAP_TOL*100)}% of anchor price.")
    lines.append("- candles come from Binance Vision (cloud friendly).")
    lines.append("- info only, not financial advice.")
    return "\n".join(lines)


# ---------- Telegram handlers ----------
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Bot online.\nCommands:\n/start\n/daily\n/sources"
    )


async def sources_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Sources:\n- Binance Vision (candles)\n- Kraken (spot last price)\n- Coinbase Exchange (spot last price)\n- CoinGecko (market price/volume)\n"
    )


async def daily_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Running analysis... (5-20s)")
    try:
        text = build_report(top_n=5)
        await update.message.reply_text(text)
    except Exception as e:
        await update.message.reply_text(f"Error: {type(e).__name__}: {e}")


def main() -> None:
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("daily", daily_cmd))
    app.add_handler(CommandHandler("sources", sources_cmd))
    app.run_polling()


if __name__ == "__main__":
    main()