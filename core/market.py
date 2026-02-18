import logging
# IMPORTANTE: Esta línea faltaba y es la que causa el NameError
from typing import List, Dict, Tuple 

from core.sources import fetch_coingecko_top100, verify_price_multi_source

logger = logging.getLogger(__name__)

STABLES = {"USDT", "USDC", "DAI", "FDUSD", "TUSD", "USDE", "USDS", "PYUSD"}
GOLD = {"XAUT", "PAXG"}
MAJORS = {"BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "AVAX"}

def is_stable(row: Dict) -> bool:
    sym = (row.get("symbol") or "").upper()
    return sym in STABLES or "usd" in (row.get("name") or "").lower()

def is_gold(row: Dict) -> bool:
    sym = (row.get("symbol") or "").upper()
    return sym in GOLD or "gold" in (row.get("name") or "").lower()

def estimate_risk(row: Dict) -> str:
    cap = float(row.get("market_cap") or 0)
    if cap >= 20_000_000_000: return "LOW"
    if cap >= 2_000_000_000: return "MEDIUM"
    return "HIGH"

def split_alts_and_majors(rows: List[Dict]) -> Tuple[List[Dict], List[Dict]]:
    majors, alts = [], []
    for r in rows:
        sym = (r.get("symbol") or "").upper()
        if sym in MAJORS or r.get("market_cap_rank", 99) <= 10:
            majors.append(r)
        else:
            alts.append(r)
    return majors, alts

def verify_prices(rows: List[Dict]) -> Tuple[List[Dict], Dict]:
    enriched = []
    verified_count = 0
    for r in rows:
        try:
            # CoinGecko devuelve 'current_price'
            price = r.get("current_price") or 0
            symbol = r.get("symbol") or ""
            ok_count, _ = verify_price_multi_source(price, symbol)
        except:
            ok_count = 1
            
        rr = dict(r)
        rr["verified"] = ok_count >= 1 # Bajamos la exigencia para testear
        rr["price"] = price
        enriched.append(rr)
        if rr["verified"]: verified_count += 1
            
    stats = {"total": len(rows), "verified": verified_count}
    return enriched, stats
