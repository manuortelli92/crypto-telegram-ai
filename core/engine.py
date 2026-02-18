import os
import json
import logging
from typing import List, Dict, Optional

# --- REPARACIÓN DE IMPORTS ---
# fetch_coingecko_top100 viene de SOURCES
from core.sources import fetch_coingecko_top100 

# El resto de la lógica de limpieza y verificación viene de MARKET
from core.market import (
    verify_prices, 
    split_alts_and_majors, 
    estimate_risk, 
    is_stable, 
    is_gold
)

from core.learning import get_learning_boost
from core.llm_gemini import gemini_render
from core.news import get_news_summary_for_llm

logger = logging.getLogger(__name__)

# --- Helpers de formato ---
def pct(x: Optional[float]) -> str:
    if x is None: return "n/a"
    return f"{float(x):+.2f}%"

def price_fmt(p: Optional[float]) -> str:
    if p is None: return "n/a"
    p = float(p)
    if p >= 1000: return f"${p:,.0f}"
    if p >= 1: return f"${p:,.2f}"
    return f"${p:.6f}"

# --- Score del Motor ---
def compute_engine_score(row: Dict) -> float:
    try:
        # Extraemos los porcentajes de cambio (CoinGecko los llama price_change_percentage_...)
        mom7 = float(row.get("price_change_percentage_7d_in_currency") or 0)
        mom30 = float(row.get("price_change_percentage_30d_in_currency") or 0)
        base = (mom7 * 0.65) + (mom30 * 0.35)
        
        # Bonus por consistencia alcista
        consistency = 5.0 if (mom7 > 0 and mom30 > 0) else -3.0 if (mom7 < 0 and mom30 < 0) else 0
        
        # Penalización si el spread entre exchanges es bardo
        trust_penalty = 0.0 if row.get("verified", True) else -7.0
        
        learn = float(get_learning_boost(row.get("symbol", "")) or 0)
        return base + consistency + trust_penalty + learn
    except:
        return 0.0

# --- Lógica Principal ---
def build_engine_analysis(user_text: str, chat_id: int, state: Dict) -> str:
    # 1. Obtener datos crudos desde SOURCES
    raw_rows = fetch_coingecko_top100()
    if not raw_rows:
        return "Che, no pude conectar con los servidores de precios. Bancame un toque que se enfrió la API."

    # 2. Verificar y filtrar usando MARKET
    rows, v_stats = verify_prices(raw_rows)
    rows = [r for r in rows if not is_stable(r) and not is_gold(r)]

    for r in rows:
        # Adaptamos nombres de campos de CoinGecko si hace falta
        r["price"] = r.get("current_price", 0)
        r["mom_7d"] = r.get("price_change_percentage_7d_in_currency", 0)
        r["mom_30d"] = r.get("price_change_percentage_30d_in_currency", 0)
        
        r["engine_score"] = compute_engine_score(r)
        r["risk"] = estimate_risk(r)
    
    rows.sort(key=lambda x: x["engine_score"], reverse=True)

    # 3. ¿Es una consulta por una moneda específica?
    tokens = user_text.upper().replace("?", "").split()
    for r in rows:
        sym = r.get("symbol", "").upper()
        if sym in tokens:
            v_status = "✅ Verificado" if r.get('verified') else "⚠️ Spread Alto"
            return (
                f"📊 *{sym} ({r['name']})*\n\n"
                f"💰 Precio: {price_fmt(r['price'])}\n"
                f"🔍 Status: {v_status}\n"
                f"⚡ Score: {r['engine_score']:.1f} | Riesgo: {r['risk']}\n"
                f"📈 7d: {pct(r['mom_7d'])} | 30d: {pct(r['mom_30d'])}\n"
            )

    # 4. Análisis General con Gemini
    top_picks = rows[:12]
    
    news = get_news_summary_for_llm(5)
    
    payload = {
        "stats": v_stats,
        "picks": [{"s": r["symbol"], "score": round(r["engine_score"], 1), "v": r["verified"]} for r in top_picks]
    }

    system_prompt = (
        "Sos OrtelliCryptoAI, un analista de Argentina. Hablás como un experto de la city pero con onda (che, vos, timba, holdear). "
        "No des consejos financieros. Analizá los datos y las noticias. Si ves algo verificado (v:true), dale más peso."
    )
    
    user_prompt = f"NOTICIAS:\n{news}\n\nDATOS:\n{json.dumps(payload)}\n\nPREGUNTA USUARIO: {user_text}"

    # Llamada a Gemini
    fallback = "Mirá, el mercado está movido y mi conexión con el satélite de Google falló. Según mis datos, lo mejorcito ahora es: " + ", ".join([r["symbol"].upper() for r in top_picks[:5]])
    
    return gemini_render(system_prompt, user_prompt) or fallback
