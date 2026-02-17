import os
import time
import math
import logging
from typing import List, Dict, Tuple, Optional

import requests
import numpy as np

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("Missing BOT_TOKEN env var. Set it in Railway > Variables.")

# Config (you can override with Railway Variables if you want)
TIMEFRAME = os.getenv("TIMEFRAME", "1d")          # Binance interval
CANDLE_LIMIT = int(os.getenv("CANDLE_LIMIT", "200"))
PRICE_GAP_TOL = float(os.getenv("PRICE_GAP_TOL", "0.02"))  # 2%

BINANCE_KLINES_URL = "https://api.binance.com/api/v3/klines"
COINGECKO_MARKETS_URL = "https://api.coingecko.com/api/v3/coins/markets"

# (name, binance_symbol, coingecko_id)
UNIVERSE: List[Tuple[str, str, str]] = [
    ("Bitcoin", "BTCUSDT", "bitcoin"),
    ("Ethereum", "ETHUSDT", "ethereum"),
    ("Solana", "SOLUSDT", "solana"),
    ("BNB", "BNBUSDT", "binancecoin"),
    ("XRP", "XRPUSDT", "ripple"),
    ("Cardano", "ADAUSDT", "cardano"),
    ("Avalanche", "AVAXUSDT", "avalanche-2"),
    ("Chainlink", "LINKUSDT", "chainlink"),
]


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


def fetch_coingecko_markets(ids: List[str]) -> List[Dict]:
    r = requests.get(
        COINGECKO_MARKETS_URL,
        params={"vs_currency": "usd", "ids": ",".join(ids), "per_page": 250, "page": 1},
        timeout=25,
    )
    r.raise_for_status()
    return r.json()


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


def score_asset(feat: Dict[str, float], vol24h_usd: Optional[float], verified: bool) -> Dict[str, object]:
    mom_7d = feat["mom_7d"]
    mom_30d = feat["mom_30d"]
    vol = feat["vol_30d"]
    dd = feat["dd_30d"]

    s = 50.0
    s += 25.0 * math.tanh(3.0 * mom_30d)
    s += 10.0 * math.tanh(5.0 * mom_7d)
    s -= 10.0 * math.tanh(2.0 * vol)
    s -= 12.0 * math.tanh(5.0 * abs(dd))

    if vol24h_usd is None:
        s -= 8.0
    else:
        if vol24h_usd < 10_000_000:
            s -= 12.0
        elif vol24h_usd < 50_000_000:
            s -= 6.0
        elif vol24h_usd > 200_000_000:
            s += 6.0

    if not verified:
        s -= 25.0

    s = float(max(0.0, min(100.0, s)))

    risk = "LOW"
    if vol > 0.9 or (vol24h_usd is not None and vol24h_usd < 10_000_000):
        risk = "HIGH"
    elif vol > 0.6 or abs(dd) > 0.20:
        risk = "MEDIUM"

    return {"score": s, "risk": risk}


def fmt_pct(x: float) -> str:
    return f"{x * 100:.2f}%"


def build_report(top_n: int = 5) -> str:
    ids = [cg_id for _, _, cg_id in UNIVERSE]
    cg_list = fetch_coingecko_markets(ids)
    cg_map = {m["id"]: m for m in cg_list}

    rows = []
    for name, bsymbol, cg_id in UNIVERSE:
        m = cg_map.get(cg_id, {})
        cg_price = m.get("current_price")
        cg_vol = m.get("total_volume")

        verified = True
        closes = []
        last_close = None

        try:
            closes, last_close = fetch_binance_closes(bsymbol, TIMEFRAME, CANDLE_LIMIT)
        except Exception:
            verified = False

        if cg_price and last_close:
            gap = abs(float(cg_price) - float(last_close)) / float(cg_price)
            if gap > PRICE_GAP_TOL:
                verified = False

        feat = features_from_closes(closes) if closes else {"mom_7d": 0.0, "mom_30d": 0.0, "vol_30d": 0.0, "dd_30d": 0.0}
        scored = score_asset(feat, vol24h_usd=cg_vol, verified=verified)

        rows.append({
            "name": name,
            "symbol": bsymbol,
            "score": scored["score"],
            "risk": scored["risk"],
            "mom_30d": feat["mom_30d"],
            "vol_30d": feat["vol_30d"],
            "verified": verified,
        })

    rows.sort(key=lambda x: float(x["score"]), reverse=True)
    top = rows[:top_n]

    lines = []
    lines.append("Crypto Brief (verified)")
    lines.append(time.strftime("Generated UTC: %Y-%m-%d %H:%M:%S", time.gmtime()))
    lines.append("")
    lines.append("Top options (you decide):")
    for i, r in enumerate(top, 1):
        lines.append(
            f"{i}) {r['name']} ({r['symbol']}) | Score {r['score']:.1f} | Risk {r['risk']} | "
            f"Mom30d {fmt_pct(float(r['mom_30d']))} | Verified {r['verified']}"
        )
    lines.append("")
    lines.append("Verification: Binance klines + CoinGecko markets; if price gap > "
                 f"{int(PRICE_GAP_TOL * 100)}% then NOT verified and score is penalized.")
    lines.append("Info only, not financial advice.")
    return "\n".join(lines)


async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Bot is online.\nCommands:\n/start\n/daily\n"
    )


async def daily_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Running analysis... (5-15s)")
    try:
        text = build_report(top_n=5)
        await update.message.reply_text(text)
    except Exception as e:
        await update.message.reply_text(f"Error: {type(e).__name__}: {e}")


def main() -> None:
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("daily", daily_cmd))
    app.run_polling()


if __name__ == "__main__":
    main()