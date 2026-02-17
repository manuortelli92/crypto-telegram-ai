import requests
from datetime import datetime

COINGECKO_URL = "https://api.coingecko.com/api/v3/coins/markets"

def fmt_pct(v):
    if v is None:
        return "n/a"
    return f"{v:.2f}%"

# ----------------------------------------------------
# DATA FETCH
# ----------------------------------------------------

def get_market_data(vs="usd", per_page=80):

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

# ----------------------------------------------------
# MARKET STRUCTURE SCORING
# ----------------------------------------------------

def compute_structure_score(row):

    mom7 = row.get("price_change_percentage_7d_in_currency") or 0
    mom30 = row.get("price_change_percentage_30d_in_currency") or 0
    volume = row.get("total_volume") or 0
    cap = row.get("market_cap") or 1

    # 1) Momentum corto
    trend_short = mom7 * 0.6

    # 2) Estructura media
    trend_mid = mom30 * 0.4

    # 3) Consistencia estructural
    structure_bonus = 0
    if mom7 > 0 and mom30 > 0:
        structure_bonus = 6
    elif mom7 > 0 and mom30 < 0:
        structure_bonus = -4

    # 4) Volumen relativo
    vol_ratio = volume / cap if cap else 0
    vol_score = min(vol_ratio * 120, 12)

    # 5) Penalización por debilidad fuerte
    weakness_penalty = 0
    if mom30 < -45:
        weakness_penalty = -15
    elif mom30 < -25:
        weakness_penalty = -6

    score = (
        trend_short +
        trend_mid +
        structure_bonus +
        vol_score +
        weakness_penalty
    )

    return score

# ----------------------------------------------------

def classify_risk(score):

    if score >= 25:
        return "HIGH"
    elif score >= 12:
        return "MEDIUM"
    else:
        return "LOW"

# ----------------------------------------------------

def get_ranked_market(prefs):

    data = get_market_data()

    avoid = prefs.get("avoid", [])

    rows = []

    for d in data:

        symbol = d["symbol"].upper()

        if symbol in avoid:
            continue

        score = compute_structure_score(d)

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
        "timeframe": "structure hybrid",
        "tol": 0.02,
        "rows": rows
    }