import os
import json
import logging
from typing import List, Dict, Optional

# Imports corregidos
from core.sources import fetch_coingecko_top100 
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

def pct(x: Optional[float]) -> str:
    if x is None: return "0.00%"
    return f"{float(x):+.2f}%"

def price_fmt(p: Optional[float]) -> str:
    if not p: return "n/a"
    p = float(p)
    if p >= 1000: return f"${p:,.0f}"
    if p >= 1: return f"${p:,.2f}"
    return f"${p:.6f}"

def compute_engine_score(row: Dict) -> float:
    try:
        # Intentamos sacar el cambio de 7d y 24h (que son los más comunes)
        # Si no están, usamos 0 para que no rompa la cuenta
        m7 = float(row.get("price_change_percentage_7d_in_currency") or row.get("price_change_percentage_24h") or 0)
        m30 = float(row.get("price_change_percentage_30d_in_currency") or m7 or 0)
        
        base = (m7 * 0.7) + (m30 * 0.3)
        trust = 0.0 if row.get("verified", True) else -5.0
        learn = float(get_learning_boost(row.get("symbol", "")) or 0)
        
        return base + trust + learn
    except Exception as e:
        logger.error(f"Error calculando score para {row.get('symbol')}: {e}")
        return 0.0

def build_engine_analysis(user_text: str, chat_id: int, state: Dict) -> str:
    raw_rows = fetch_coingecko_top100()
    if not raw_rows:
        return "Che, CoinGecko no me está pasando los precios. Probá en un toque que seguro es el rate-limit."

    # Procesar datos
    rows, v_stats = verify_prices(raw_rows)
    rows = [r for r in rows if not is_stable(r) and not is_gold(r)]

    for r in rows:
        # Aseguramos que existan estas claves para el resto del código
        r["price"] = r.get("current_price", 0)
        r["mom_7d"] = r.get("price_change_percentage_7d_in_currency") or r.get("price_change_percentage_24h") or 0
        r["mom_30d"] = r.get("price_change_percentage_30d_in_currency") or r["mom_7d"]
        r["engine_score"] = compute_engine_score(r)
        r["risk"] = estimate_risk(r)
    
    rows.sort(key=lambda x: x.get("engine_score", 0), reverse=True)

    # 1. Búsqueda por Símbolo
    query = user_text.upper().strip()
    for r in rows:
        if r.get("symbol", "").upper() == query or f"/{r.get('symbol','')}".upper() == query:
            v_status = "✅ Verificado" if r.get('verified') else "⚠️ Spread"
            return (
                f"📊 *{r['symbol'].upper()} ({r['name']})*\n\n"
                f"💰 Precio: {price_fmt(r['price'])}\n"
                f"🔍 Status: {v_status}\n"
                f"⚡ Score: {r['engine_score']:.1f}\n"
                f"📈 7d: {pct(r['mom_7d'])}\n"
            )

    # 2. Si no es símbolo, vamos con Gemini
    top_picks = rows[:10]
    news = get_news_summary_for_llm(3)
    
    payload = {
        "top": [{"s": r["symbol"], "p": r["price"], "sc": round(r["engine_score"],1)} for r in top_picks]
    }

    sys_prompt = "Sos OrtelliCryptoAI, analista financiero argentino. Usá términos como 'holdear', 'shitcoin', 'to the moon'. Sé breve y directo."
    user_prompt = f"Datos Mercado: {json.dumps(payload)}\nNoticias: {news}\nPregunta: {user_text}"

    # Fallback si Gemini falla
    res = gemini_render(sys_prompt, user_prompt)
    if not res:
        res = "El satélite de Google está caído, pero acá tenés los que más están rindiendo:\n\n"
        for r in top_picks[:5]:
            res += f"• {r['symbol'].upper()}: Score {r['engine_score']:.1f}\n"
            
    return res
