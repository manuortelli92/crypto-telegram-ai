import os, json, logging, traceback
from typing import List, Dict, Optional, Any

from core.sources import fetch_coingecko_top100 
from core.market import verify_prices, is_stable, is_gold
# IMPORTACIONES SINCRONIZADAS
from core.brain import apply_patch_to_session, add_turn, save_brain_state
from core.learning import register_user_interest, get_learning_boost
from core.llm_gemini import gemini_render

try:
    from core.news import get_news_summary_for_llm
except ImportError:
    def get_news_summary_for_llm(): return "No hay noticias disponibles."

logger = logging.getLogger(__name__)

def build_engine_analysis(user_text: str, chat_id: int, state: Dict) -> str:
    try:
        # 1. BRAIN: Registrar turno del usuario
        add_turn(state, chat_id, "user", user_text)
        
        # 2. BRAIN: Obtener contexto y preferencias personales
        user_prefs = apply_patch_to_session(state, chat_id, user_text)
        
        # 3. LEARNING: Registrar interés en tickers mencionados
        register_user_interest(user_text)

        # 4. MERCADO: Obtener datos
        raw_rows = fetch_coingecko_top100()
        if not raw_rows: return "❌ Error de conexión con el mercado."

        rows, _ = verify_prices(raw_rows)
        final_rows = []
        for r in rows:
            sym = r.get("symbol", "").upper()
            if is_stable(r) or is_gold(r) or sym in user_prefs.get("avoid", []):
                continue
            
            # Unimos Mercado + Learning (Boost de popularidad)
            p_change = float(r.get("price_change_percentage_24h") or 0)
            pop_boost = get_learning_boost(sym)
            focus_boost = 5.0 if sym in user_prefs.get("focus", []) else 0.0
            
            r["engine_score"] = p_change + pop_boost + focus_boost
            final_rows.append(r)

        final_rows.sort(key=lambda x: x.get("engine_score", 0), reverse=True)

        # 5. Ticker directo (CORREGIDO)
        query = user_text.upper().strip().replace("$", "")
        for r in final_rows:
            current_sym = r.get("symbol", "").upper()
            if current_sym == query:
                trend = "🚀" if r.get("price_change_percentage_24h", 0) > 0 else "📉"
                return f"{trend} *{r['name']} ({current_sym})*\n💰 Precio: ${r.get('current_price'):,}\n📊 Var. 24h: {r.get('price_change_percentage_24h'):.2f}%"

        # 6. Preparar Gemini
        top_limit = user_prefs.get("top_n", 20)
        market_summary = [{"s": r['symbol'].upper(), "p": r['current_price'], "c": f"{r['price_change_percentage_24h']:.1f}%"} for r in final_rows[:top_limit]]
        
        sys_prompt = "Sos un analista financiero experto (City argentina). Usá negritas para tickers."
        user_prompt = (
            f"HISTORIAL:\n{user_prefs.get('context')}\n\n"
            f"PREFERENCIAS: Riesgo {user_prefs.get('risk_pref')}. Foco en: {user_prefs.get('focus')}\n\n"
            f"DATOS: {json.dumps(market_summary)}\n\n"
            f"NOTICIAS: {get_news_summary_for_llm()}\n\n"
            f"PREGUNTA: {user_text}"
        )

        ai_res = gemini_render(sys_prompt, user_prompt)
        
        if ai_res and "Error" not in ai_res:
            add_turn(state, chat_id, "bot", ai_res) # BRAIN: Guardar respuesta bot
            save_brain_state(state) # PERSISTENCIA FINAL
            
        return ai_res or "⚠️ La IA no respondió."

    except Exception as e:
        logger.error(f"💥 ERROR: {traceback.format_exc()}")
        return f"🤯 Cortocircuito: `{str(e)}`"
