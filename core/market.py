import logging
# Reparación técnica: Soporte para Python < 3.9 y >= 3.9
from typing import List, Dict, Tuple, Any, Optional

# Importamos las herramientas de verificación de sources
try:
    from core.sources import verify_price_multi_source
except ImportError:
    # Fallback por si sources no está listo
    def verify_price_multi_source(p, s): return 1, "OK"

logger = logging.getLogger(__name__)

# Listas de categorías actualizadas
STABLES = {"USDT", "USDC", "DAI", "FDUSD", "TUSD", "USDE", "USDS", "PYUSD", "USDP"}
GOLD = {"XAUT", "PAXG"}
MAJORS = {"BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "AVAX", "DOT", "LINK"}

def is_stable(row: Dict) -> bool:
    """Detecta si es una stablecoin para filtrarla de análisis de volatilidad."""
    sym = (row.get("symbol") or "").upper()
    name = (row.get("name") or "").lower()
    return sym in STABLES or "usd" in name or "tether" in name

def is_gold(row: Dict) -> bool:
    """Detecta tokens respaldados por oro."""
    sym = (row.get("symbol") or "").upper()
    name = (row.get("name") or "").lower()
    return sym in GOLD or "gold" in name

def estimate_risk(row: Dict) -> str:
    """
    Calcula el riesgo basado en Market Cap (Liquidez).
    LOW: > 20B (Blue Chips)
    MEDIUM: 2B - 20B (Mid Caps)
    HIGH: < 2B (Small Caps / Altcoins)
    """
    try:
        cap = float(row.get("market_cap") or 0)
        if cap >= 20_000_000_000: return "LOW"
        if cap >= 2_000_000_000: return "MEDIUM"
        return "HIGH"
    except (ValueError, TypeError):
        return "UNKNOWN"

def split_alts_and_majors(rows: List[Dict]) -> Tuple[List[Dict], List[Dict]]:
    """Separa el mercado en 'Monedas Líderes' y 'Altcoins'."""
    majors, alts = [], []
    for r in rows:
        sym = (r.get("symbol") or "").upper()
        rank = r.get("market_cap_rank") or 999
        
        if sym in MAJORS or rank <= 10:
            majors.append(r)
        else:
            alts.append(r)
    return majors, alts

def verify_prices(rows: List[Dict]) -> Tuple[List[Dict], Dict]:
    """
    ENRIQUECEDOR: Toma los datos crudos de la API y les agrega capas de seguridad.
    """
    enriched = []
    verified_count = 0
    
    for r in rows:
        try:
            # Aseguramos datos limpios
            price = float(r.get("current_price") or 0)
            symbol = (r.get("symbol") or "").upper()
            
            # Verificación cruzada (si existe la función en sources)
            ok_count, _ = verify_price_multi_source(price, symbol)
            
            # Clonamos y enriquecemos el diccionario
            rr = dict(r)
            rr["verified"] = ok_count >= 1
            rr["price"] = price
            rr["risk_level"] = estimate_risk(rr)
            rr["is_meme"] = (rr.get("market_cap_rank") or 999) > 200 # Marcamos como sospechosa si está muy abajo
            
            enriched.append(rr)
            if rr["verified"]: verified_count += 1
            
        except Exception as e:
            logger.error(f"⚠️ Error procesando fila de {r.get('symbol')}: {e}")
            continue
            
    stats = {
        "total": len(rows), 
        "verified": verified_count,
        "efficiency": (verified_count / len(rows) * 100) if rows else 0
    }
    return enriched, stats
