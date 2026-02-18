import logging
from typing import List, Dict, Tuple

# IMPORTANTE: Re-exportamos la función desde sources para que el engine la encuentre aquí
from core.sources import fetch_coingecko_top100, verify_price_multi_source

logger = logging.getLogger(__name__)

# Configuración de activos
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
    Función que el engine llama para validar precios.
    """
    enriched = []
    verified_count = 0
    
    for r in rows:
        # Llamamos a la lógica de fuentes que definimos en sources.py
        ok_count, sources_str = verify_price_multi_source(r["price"], r["symbol"])
        
        rr = dict(r)
        rr["verified"] = ok_count >= 2
        rr["price_anchor"] = r["price"] 
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
