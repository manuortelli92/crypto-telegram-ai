import logging
from typing import List, Dict, Tuple

# Importamos la fuerza bruta desde sources
from core.sources import fetch_coingecko_top100, verify_price_multi_source

logger = logging.getLogger(__name__)

# Listas negras para no recomendar cosas que no son inversión
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
        if sym in MAJORS or r.get("rank", 99) <= 10:
            majors.append(r)
        else:
            alts.append(r)
    return majors, alts

def verify_prices(rows: List[Dict]) -> Tuple[List[Dict], Dict]:
    """
    Esta es la función que el engine busca. 
    Enriquece cada moneda con la verificación multi-fuente.
    """
    enriched = []
    verified_count = 0
    
    for r in rows:
        # Usamos la función de sources.py
        ok_count, sources_str = verify_price_multi_source(r["price"], r["symbol"])
        
        rr = dict(r)
        rr["verified"] = ok_count >= 2
        rr["price_anchor"] = r["price"] # En esta versión usamos el de CG como base
        rr["sources_ok"] = ok_count
        enriched.append(rr)
        
        if rr["verified"]:
            verified_count += 1
            
    stats = {
        "total": len(rows),
        "verified": verified_count,
        "verified_pct": (verified_count / len(rows) * 100) if rows else 0
    }
    return enriched, stats
