import requests

MAJORS = ["BTC", "ETH"]

COINGECKO_URL = "https://api.coingecko.com/api/v3/coins/markets"


def fetch_top100_market():

    params = {
        "vs_currency": "usd",
        "order": "market_cap_desc",
        "per_page": 100,
        "page": 1,
        "price_change_percentage": "7d,30d"
    }

    r = requests.get(COINGECKO_URL, params=params, timeout=20)
    r.raise_for_status()

    data = r.json()

    rows = []

    for coin in data:

        symbol = coin.get("symbol", "").upper()

        entry = {
            "symbol": symbol,
            "price": coin.get("current_price", 0),
            "mom_7d": coin.get("price_change_percentage_7d_in_currency", 0) or 0,
            "mom_30d": coin.get("price_change_percentage_30d_in_currency", 0) or 0,
            "sources_ok": 4,
            "risk": estimate_risk(coin)
        }

        rows.append(entry)

    return rows


def estimate_risk(coin):

    mcap = coin.get("market_cap", 0)

    if mcap > 200_000_000_000:
        return "LOW"
    if mcap > 30_000_000_000:
        return "MEDIUM"
    return "HIGH"


def is_alt(symbol: str) -> bool:
    return symbol not in MAJORS


def split_alts_and_majors(rows):

    majors = []
    alts = []

    for r in rows:
        if is_alt(r["symbol"]):
            alts.append(r)
        else:
            majors.append(r)

    return majors, alts


def rank_top(rows, limit=20):

    ranked = sorted(
        rows,
        key=lambda x: (x["mom_7d"] * 0.6 + x["mom_30d"] * 0.4),
        reverse=True
    )

    return ranked[:limit]