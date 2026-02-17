import requests

COINGECKO_URL = "https://api.coingecko.com/api/v3/coins/markets"

# Lista explícita (además de Top10 por cap) para clasificar como NO-ALTS
MAJORS_SET = {"BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "AVAX", "DOGE", "DOT", "TRX", "LINK"}

# Stablecoins típicas (símbolos) para filtrar
STABLES = {
    "USDT","USDC","DAI","TUSD","FDUSD","USDE","USDS","FRAX","LUSD","PYUSD","GUSD","USDP",
    "USD1","RLUSD","USDG","GHO"
}

GOLD = {"XAUT", "PAXG"}

def fetch_top100_market(vs="usd"):
    params = {
        "vs_currency": vs,
        "order": "market_cap_desc",
        "per_page": 100,
        "page": 1,
        "sparkline": False,
        "price_change_percentage": "7d,30d",
    }
    r = requests.get(COINGECKO_URL, params=params, timeout=25)
    r.raise_for_status()

    data = r.json()
    rows = []
    for idx, coin in enumerate(data, start=1):
        symbol = (coin.get("symbol") or "").upper().strip()
        name = (coin.get("name") or "").strip()

        rows.append({
            "rank": idx,  # rank por market cap (1..100)
            "id": coin.get("id"),
            "symbol": symbol,
            "name": name,
            "price": coin.get("current_price", 0) or 0,
            "market_cap": coin.get("market_cap", 0) or 0,
            "volume_24h": coin.get("total_volume", 0) or 0,
            "mom_7d": coin.get("price_change_percentage_7d_in_currency", 0) or 0,
            "mom_30d": coin.get("price_change_percentage_30d_in_currency", 0) or 0,
        })
    return rows

ddef is_stable(row) -> bool:
    sym = row.get("symbol", "")
    if sym in STABLES:
        return True

    name = (row.get("name") or "").lower()
    if ("stable" in name) or ("usd" in name and ("coin" in name or "dollar" in name or "stable" in name)):
        return True

    # heurística: precio ~1 y cambios muy chicos -> probablemente stable
    p = float(row.get("price", 0) or 0)
    m7 = float(row.get("mom_7d", 0) or 0)
    m30 = float(row.get("mom_30d", 0) or 0)
    if 0.985 <= p <= 1.015 and abs(m7) < 1.0 and abs(m30) < 2.0:
        return True

    return False

def is_major(row) -> bool:
    # Major si está en la lista o si está en top 10 por market cap
    sym = row.get("symbol", "")
    rank = row.get("rank", 999)
    return (sym in MAJORS_SET) or (rank <= 10)

def split_alts_and_majors(rows):
    majors, alts = [], []
    for r in rows:
        if is_major(r):
            majors.append(r)
        else:
            alts.append(r)
    return majors, alts

def estimate_risk(row) -> str:
    cap = row.get("market_cap", 0) or 0
    if cap >= 200_000_000_000:
        return "LOW"
    if cap >= 30_000_000_000:
        return "MEDIUM"
    return "HIGH"

def is_gold(row) -> bool:
    sym = row.get("symbol", "")
    if sym in GOLD:
        return True
    name = (row.get("name") or "").lower()
    if "gold" in name:
        return True
    return False