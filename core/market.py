import requests
from datetime import datetime

COINGECKO_URL = "https://api.coingecko.com/api/v3/coins/markets"

def fmt_pct(v):
    if v is None:
        return "n/a"
    return f"{v:.2f}%"

def get_market_data(vs="usd", per_page=50):
    params = {
        "vs_currency": vs,
        "order": "market_cap_desc",
        "per_page": per_page,
        "page": 1,
        "sparkline": False,
        "price_change_percentage": "7d,30d"
    }
    r = requests.get(COINGECKO_URL, params=params, timeout=20)
    r.raise_for_status()
    return r.json()

# --------------------------------------------------------
# NUEVO SISTEMA DE SCORING
# --------------------------------------------------------

def compute_score(row, prefs):

    mom7 = row.get("price_change_percentage_7d_in_currency") or 0
    mom30 = row.get("price_change_percentage_30d_in_currency") or 0
    volume = row.get("total_volume") or 0
    cap = row.get("market_cap") or 1

    # Momentum corto
    trend_short = mom7 * 0.5

    # Estructura media
    trend_mid = mom30 * 0.3

    # Volumen relativo
    vol_ratio = volume / cap if cap else 0
    vol_score = min(vol_ratio * 100, 10)

    # Penalización si 30d muy negativo
    penalty = 0
    if mom30 < -40:
        penalty = -10

    score = trend_short + trend_mid + vol_score + penalty

    return score

# --------------------------------------------------------

def classify_risk(score):
    if score > 20:
        return "HIGH"
    if score > 10:
        return "MEDIUM"
    return "LOW"

# --------------------------------------------------------

def get_ranked_market(prefs):

    data = get_market_data()

    rows = []

    for d in data:

        symbol = d["symbol"].upper()

        avoid = prefs.get("avoid", [])
        if symbol in avoid:
            continue

        score = compute_score(d, prefs)

        row = {
            "name": d["name"],
            "symbol": symbol,
            "score": score,
            "risk": classify_risk(score),
            "mom_7d": d.get("price_change_percentage_7d_in_currency"),
            "mom_30d": d.get("price_change_percentage_30d_in_currency"),
        }

        rows.append(row)

    rows.sort(key=lambda x: x["score"], reverse=True)

    return {
        "generated_utc": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "timeframe": "7d+30d hybrid",
        "tol": 0.02,
        "rows": rows
    }