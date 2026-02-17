import os
import math
import time
import requests
import numpy as np
import logging

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("Falta BOT_TOKEN en Railway > Variables")

# === Config básica ===
TIMEFRAME = os.getenv("TIMEFRAME", "1d")   # binance interval
LIMIT = int(os.getenv("CANDLE_LIMIT", "200"))
PRICE_GAP_TOL = float(os.getenv("PRICE_GAP_TOL", "0.02"))  # 2%

# Universo inicial (lo ampliamos después)
UNIVERSE = [
    ("Bitcoin",  "BTCUSDT", "bitcoin"),
    ("Ethereum", "ETHUSDT", "ethereum"),
    ("Solana",   "SOLUSDT", "solana"),
    ("BNB",      "BNBUSDT", "binancecoin"),
    ("XRP",      "XRPUSDT", "ripple"),
    ("Cardano",  "ADAUSDT", "cardano"),
    ("Avalanche","AVAXUSDT","avalanche-2"),
    ("Chainlink","LINKUSDT","chainlink"),
]

BINANCE_KLINES = "https://api.binance.com/api/v3/klines"
COINGECKO_MARKETS = "https://api.coingecko.com/api/v3/coins/markets"
DEFILLAMA_PROTOCOLS = "https://api.llama.fi/protocols"


def fetch_binance_klines(symbol: str, interval: str, limit: int):
    r = requests.get(
        BINANCE_KLINES,
        params={"symbol": symbol, "interval": interval, "limit": limit},
        timeout=25
    )
    r.raise_for_status()
    data = r.json()
    closes = [float(k[4]) for k in data]
    last_close = float(data[-1][4]) if data else None
    return closes, last_close


def coingecko_markets(ids: list[str]):
    r = requests.get(
        COINGECKO_MARKETS,
        params={"vs_currency": "usd", "ids": ",".join(ids), "per_page": 250, "page": 1},
        timeout=25
    )
    r.raise_for_status()
    return r.json()


def defillama_index():
    r = requests.get(DEFILLAMA_PROTOCOLS, timeout=30)
    r.raise_for_status()
    idx = {}
    for p in r.json():
        name = (p.get("name") or "").strip().lower()
        if name:
            idx[name] = {
                "tvl": p.get("tvl"),
                "category": p.get("category"),
                "url": p.get("url"),
            }
    return idx


def pct_change(a: float, b: float) -> float:
    if a == 0:
        return 0.0
    return (b - a) / a


def features_from_closes(closes: list[float]) -> dict:
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


def score_asset(feat: dict, vol24h_usd: float | None, verified: bool, has_defi: bool) -> dict:
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

    if has_defi:
        s += 4.0

    if not verified:
        s -= 25.0

    s = max(0.0, min(100.0, float(s)))

    risk = "LOW"
    if vol > 0.9 or (vol24h_usd is not None and vol24h_usd < 10_000_000):
        risk = "HIGH"
    elif vol > 0.6 or abs(dd) > 0.20:
        risk = "MEDIUM"

    return {"score": s, "risk": risk}


def fmt_pct(x: float) -> str:
    return f"{x*100:.2f}%"


def build_report(top_n: int = 5) -> str:
    ids = [cg for _, _, cg in UNIVERSE]
    cg = coingecko_markets(ids)
    cg_map = {m["id"]: m for m in cg}
    defi = defillama_index()

    rows = []
    for name, bsymbol, cg_id in UNIVERSE:
        m = cg_map.get(cg_id, {})
        cg_price = m.get("current_price")
        cg_vol = m.get("total_volume")
        cg_mcap = m.get("market_cap")

        verified = True
        price_ok = True

        closes = []
        last_close = None
        try:
            closes, last_close = fetch_binance_klines(bsymbol, TIMEFRAME, LIMIT)
        except Exception:
            verified = False

        if cg_price and last_close:
            gap = abs(cg_price - last_close) / cg_price
            if gap > PRICE_GAP_TOL:
                price_ok = False
                verified = False

        feat = features_from_closes(closes) if closes else {"mom_7d": 0.0, "mom_30d": 0.0, "vol_30d": 0.0, "dd_30d": 0.0}

        dl = defi.get(name.lower())
        has_defi = dl is not None

        scored = score_asset(feat, vol24h_usd=cg_vol, verified=verified, has_defi=has_defi)

        rows.append({
            "name": name,
            "sym": bsymbol,
            "score": scored["score"],
            "risk": scored["risk"],
            "mom_30d": feat["mom_30d"],
            "vol_30d": feat["vol_30d"],
            "verified": verified,
            "cg_price": cg_price,
            "bn_close": last_close,
            "price_ok": price_ok,
            "cg_vol": cg_vol,
            "cg_mcap": cg_mcap,
            "tvl": (dl.get("tvl") if dl else None),
        })

    rows.sort(key=lambda x: x["score"], reverse=True)
    top = rows[:top_n]

    lines = []
    lines.append("🧠 Weekly/Daily Crypto Brief (verificado)")
    lines.append(f"🕒 {time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())} UTC")
    lines.append("")
    lines.append("Top opciones (vos decidís):")

    for i, r in enumerate(top, 1):
        tvl_txt = f" | TVL: {int(r['tvl']):,}" if isinstance(r["tvl"], (int, float)) else ""
        lines.append(
            f"{i}) {r['name']} ({r['sym']}) — Score {r['score']:.1f} | Risk {r['risk']} | "
            f"Mom30d {fmt_pct(r['mom_30d'])} | Verified {r['verified']}{tvl_txt}"
        )

    lines.append("")
    lines.append("Verificación:")
    lines.append("- Binance klines (histórico) + CoinGecko (market data).")
    lines.append(f"- Si gap de precio > {PRICE_GAP_TOL*100:.0f}% → NO verificado y penaliza score.")
    lines.append("_Info, no asesoramiento financiero._")
    return "\n".join(lines)


# === Telegram handlers ===
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Estoy online.\n\nComandos:\n/daily\n/weekly\n\nTe devuelvo opciones con verificación (Binance + CoinGecko)."
    )


async def daily_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Analizando... (puede tardar 5-15s)")
    text = build_report(top_n=5)
    await update.message.reply_text(text)


async def weekly_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Armando brief semanal... (puede tardar 5-15s)")
    text = build_report(top_n=7)
    await update.message.reply_text(text)


def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("daily", daily_cmd))
    app.add_handler(CommandHandler("weekly", weekly_cmd))

    app.run_polling()


if __name__ == "__main__":
    main()