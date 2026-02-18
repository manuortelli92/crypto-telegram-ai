import os
import json
import logging
import traceback
from typing import List, Dict, Optional

# Imports correctos
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

def build_engine_analysis(user_text: str, chat_id: int, state: Dict) -> str:
    try:
        # 1. Intentar buscar datos
        raw_rows = fetch_coingecko_top100()
        if not raw_rows:
            return "❌ Error: CoinGecko no devolvió nada. Revisá la CG_API_KEY en Railway."

        # 2. Procesar con Market
        rows, v_stats = verify_prices(raw_rows)
        
        # 3. Limpieza y Score (con protección anti-None)
        final_rows = []
        for r in rows:
            if is_stable(r) or is_gold(r): continue
            
            # Forzamos valores numéricos para que no explote la cuenta
            p_change = r.get("price_change_percentage_24h") or 0
            r["engine_score"] = float(p_change) + float(get_learning_boost(r.get("symbol", "")) or 0)
            final_rows.append(r)

        final_rows.sort(key=lambda x: x.get("engine_score", 0), reverse=True)

        # 4. Respuesta rápida si es una moneda
        query = user_text.upper().strip().replace("/", "")
        for r in final_rows:
            if r.get("symbol", "").upper() == query:
                return f"📊 *{r['name']}*\n💰 Precio: ${r.get('current_price')}\n📈 24h: {r.get('price_change_percentage_24h'):.2f}%"

        # 5. Si no es moneda, llamar a Gemini
        top_10 = final_rows[:10]
        payload = {"picks": [f"{r['symbol']}: {r['engine_score']}" for r in top_10]}
        
        sys_prompt = "Sos un analista cripto argentino. Sé breve."
        user_prompt = f"Datos: {json.dumps(payload)}\nPregunta: {user_text}"
        
        ai_res = gemini_render(sys_prompt, user_prompt)
        
        if not ai_res:
            return "⚠️ Gemini no respondió. ¿Pusiste la GEMINI_API_KEY en Railway?"
            
        return ai_res

    except Exception as e:
        # ESTO ES LO IMPORTANTE: Nos va a decir el error real en Telegram
        error_detallado = traceback.format_exc()
        logger.error(f"Error crítico: {error_detallado}")
        return f"🤯 *Explotó algo internamente:*\n`{str(e)}`"
