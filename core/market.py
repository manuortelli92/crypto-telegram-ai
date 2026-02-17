from typing import List, Dict, Tuple
from core.sources import fetch_coingecko_top100

# Lista explícita (además de Top10 por cap) para clasificar como NO-ALTS
MAJORS_SET = {"BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "AVAX", "DOGE", "DOT", "TRX", "LINK"}

STABLES = {
    "USDT","USDC","DAI","TUSD","FDUSD","USDE","USDS","FRAX","LUSD","PYUSD","GUSD","USDP",
    "USD1","RLUSD","USDG","GHO"
}

GOLD = {"XAUT", "PAXG"}


def fetch_top100_market(vs: str = "usd") -> List[Dict]:
    data = fetch_coingecko_top100(vs=vs)
    rows: List[Dict] = []
    for idx, coin in enumerate(data, start=1):
        symbol = (coin.get("symbol") or "").upper().strip()
        name = (coin.get("name") or "").strip()
        rows.append({
            "rank": idx,
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


def is_gold(row: Dict) -> bool:
    sym = (row.get("symbol") or "").upper()
    if sym in GOLD:
        return True
    name = (row.get("name") or "").lower()
    return "gold" in name


def is_stable(row: Dict) -> bool:
    sym = (row.get("symbol") or "").upper()
    if sym in STABLES:
        return True

    name = (row.get("name") or "").lower()
    if "stable" in name:
        return True

    p = float(row.get("price", 0) or 0)
    m7 = float(row.get("mom_7d", 0) or 0)
    m30 = float(row.get("mom_30d", 0) or 0)
    if 0.985 <= p <= 1.015 and abs(m7) < 1.0 and abs(m30) < 2.0:
        return True

    return False


def is_major(row: Dict) -> bool:
    sym = (row.get("symbol") or "").upper()
    rank = int(row.get("rank", 999) or 999)
    return (sym in MAJORS_SET) or (rank <= 10)


def split_alts_and_majors(rows: List[Dict]) -> Tuple[List[Dict], List[Dict]]:
    majors, alts = [], []
    for r in rows:
        if is_major(r):
            majors.append(r)
        else:
            alts.append(r)
    return majors, alts


def estimate_risk(row: Dict) -> str:
    cap = float(row.get("market_cap", 0) or 0)
    if cap >= 200_000_000_000:
        return "LOW"
    if cap >= 30_000_000_000:
        return "MEDIUM"
    return "HIGH"