import os
import json
import logging
import traceback
from typing import List, Dict, Optional, Any

# Imports verificados
from core.sources import fetch_coingecko_top100 
from core.market import (
    verify_prices, 
    split_alts_and_majors, 
    estimate_risk, 
    is_stable, 
    is_gold
)
# Cambiamos a apply_patch_to_session que es el método robusto que reparamos antes
from core.learning import apply_patch_to_session 
from core.llm_gemini import gemini_render

# Nota: Si no tenés core/news.py todavía, esto podría fallar. 
# Lo envolvemos en un try/except preventivo.
try:
    from core.news import get_news_summary_for_llm
except ImportError:
    def get_news_summary_for_llm(): return "No hay noticias disponibles."

logger = logging.getLogger(__name__)

def build_engine_analysis(user_text: str, chat_id: int, state: Dict) -> str:
    """
    ORQUESTADOR MAESTRO: Une mercado, memoria e IA.
    """
    try:
        logger.info(f"🤖 Procesando solicitud para chat_id {chat_id}: '{user_text}'")

        # 1. Sincronizar Memoria y Preferencias (Learning)
        # Esto recupera modo, top_n, riesgo y contexto previo
        user_prefs = apply_patch_to_session(state, chat_id, user_text)
        
        # 2. Obtener Datos de Mercado (Sources)
        raw_rows = fetch_coingecko_top100()
        if not raw_rows:
            return "❌ Error: No pude conectar con el servidor de precios. Reintentá en unos segundos."

        # 3. Filtrado y Scoring (Market)
        rows, v_stats = verify_prices(raw_rows)
        
        final_rows = []
        for r in rows:
            # Filtro de Stables/Oro y Tickers prohibidos por el usuario
            symbol = r.get("symbol", "").upper()
            if is_stable(r) or is_gold(r) or symbol in user_prefs.get("avoid", []):
                continue
            
            # Cálculo de Score con boost de preferencia del usuario (focus)
            p_change = float(r.get("price_change_percentage_24h") or 0)
            focus_boost = 5.0 if symbol in user_prefs.get("focus", []) else 0.0
            
            r["engine_score"] = p_change + focus_boost
            final_rows.append(r)

        # Ordenar por score según el modo (aquí podrías expandir la lógica)
        final_rows.sort(key=lambda x: x.get("engine_score", 0), reverse=True)

        # 4. Detección de consulta específica (Ticker direct)
        query = user_text.upper().strip().replace("/", "").replace("$", "")
        for r in final_rows:
            if symbol == query:
                trend = "🚀" if r.get("price_change_percentage_24h", 0) > 0 else "📉"
                return (f"{trend} *{r['name']} ({symbol})*\n"
                        f"💰 Precio: ${r.get('current_price'):,}\n"
                        f"📊 Var. 24h: {r.get('price_change_percentage_24h'):.2f}%\n"
                        f"🏆 Ranking: #{r.get('market_cap_rank')}")

        # 5. Preparar Contexto para Gemini
        # Tomamos el Top N que el usuario pidió (o 20 por defecto)
        top_n_limit = user_prefs.get("top_n", 20)
        market_summary = [
            {
                "s": r['symbol'].upper(),
                "p": r['current_price'],
                "c": f"{r['price_change_percentage_24h']:.1f}%"
            } for r in final_rows[:top_n_limit]
        ]
        
        news = get_news_summary_for_llm()

        # Construcción del Prompt con Memoria
        sys_prompt = (
            "Sos un analista financiero experto en cripto. "
            "Tu estilo es profesional pero cercano (estilo argentino 'City'). "
            "Usá Markdown (negritas) para destacar tickers. Sé conciso."
        )
        
        user_prompt = (
            f"CONTEXTO PREVIO:\n{user_prefs.get('context', 'Sin historial.')}\n\n"
            f"PREFERENCIAS: Riesgo {user_prefs.get('risk_pref', 'Medio')}. "
            f"Foco en: {user_prefs.get('focus', 'General')}.\n\n"
            f"DATOS MERCADO:\n{json.dumps(market_summary)}\n\n"
            f"NOTICIAS:\n{news}\n\n"
            f"PREGUNTA USUARIO: {user_text}"
        )

        # 6. Llamada a la IA
        ai_res = gemini_render(sys_prompt, user_prompt)
        
        if not ai_res or "Error" in ai_res:
            return "⚠️ La IA está tomando un café. Intentá de nuevo o consultá un ticker específico (ej: BTC)."
            
        return ai_res

    except Exception as e:
        error_msg = traceback.format_exc()
        logger.error(f"💥 EXPLOSIÓN EN ENGINE: {error_msg}")
        return f"🤯 *Hubo un cortocircuito interno:*\n`{str(e)}`"
