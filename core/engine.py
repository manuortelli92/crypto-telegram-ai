import os
import json
import logging
from typing import List, Dict, Optional

# Importamos todos los módulos que estuvimos puliendo
from core.market import fetch_coingecko_top100, verify_prices, split_alts_and_majors, estimate_risk, is_stable, is_gold
from core.learning import get_learning_boost
from core.llm_gemini import gemini_render
from core.news import get_news_summary_for_llm
from core.brain import get_session # Para traer el contexto de la charla

logger = logging.getLogger(__name__)

# --- Funciones de Formateo ---
def pct(x: Optional[float]) -> str:
    if x is None: return "n/a"
    return f"{float(x):+.2f}%"

def price_fmt(p: Optional[float]) -> str:
    if p is None: return "n/a"
    p = float(p)
    if p >= 1000: return f"${p:,.0f}"
    if p >= 1: return f"${p:,.2f}"
    return f"${p:.6f}"

# --- Lógica de Puntuación ---
def compute_engine_score(row: Dict) -> float:
    try:
        mom7 = float(row.get("mom_7d") or 0)
        mom30 = float(row.get("mom_30d") or 0)
        base = (mom7 * 0.65) + (mom30 * 0.35)
        
        # Bonus por consistencia
        consistency = 6.0 if (mom7 > 0 and mom30 > 0) else -4.0 if (mom7 < 0 and mom30 < 0) else 0
        
        # Penalización si no está verificado entre exchanges
        trust_penalty = 0.0 if row.get("verified", True) else -8.0
        
        # Interés de los usuarios (Learning)
        learn = float(get_learning_boost(row.get("symbol", "")) or 0)
        
        return base + consistency + trust_penalty + learn
    except:
        return 0.0

# --- Renderizado Final ---
def llm_render_wrapped(user_text: str, payload_json: str, news_text: str, context_text: str) -> str:
    system = (
        "Sos un analista financiero experto en cripto de Argentina. Tu estilo es directo, profesional pero usando modismos locales (che, vistes, timba, holdear). "
        "No das consejos financieros, das análisis de datos. "
        "Si las noticias son negativas, sé cauteloso. Si el spread de precios es alto, avisale al usuario que no sea gil y verifique en varios exchanges."
    )
    
    user_prompt = (
        f"CONTEXTO DE LA CHARLA ANTERIOR:\n{context_text}\n\n"
        f"NOTICIAS DE ÚLTIMO MOMENTO:\n{news_text}\n\n"
        f"DATOS DE MERCADO (JSON):\n{payload_json}\n\n"
        f"PEDIDO ACTUAL DEL USUARIO: {user_text}\n\n"
        "Respondé con un análisis corto y luego tus recomendaciones (Top Picks)."
    )
    
    try:
        return gemini_render(system, user_prompt) or "Che, me quedé sin señal con el satélite de Google. Intentá de nuevo."
    except Exception as e:
        logger.error(f"Error en render: {e}")
        return "Hubo un bardo con la IA, probá en un ratito."

# --- Función Principal ---
def build_engine_analysis(user_text: str, chat_id: int, state: Dict) -> str:
    # 1. Detectar intenciones
    from core.brain import detect_mode, parse_top_n
    mode = detect_mode(user_text) or "SEMANAL"
    top_n = parse_top_n(user_text) or 20
    
    # 2. Obtener y verificar datos
    raw_rows = fetch_coingecko_top100()
    rows, v_stats = verify_prices(raw_rows)
    
    # 3. Filtrar y puntuar
    rows = [r for r in rows if r.get("symbol") and not is_stable(r) and not is_gold(r)]
    for r in rows:
        r["engine_score"] = compute_engine_score(r)
        r["risk"] = estimate_risk(r)
    
    rows.sort(key=lambda x: x["engine_score"], reverse=True)

    # 4. Caso: El usuario pregunta por una moneda específica
    tokens = user_text.upper().replace("?", "").split()
    for r in rows:
        if r["symbol"] in tokens:
            v_msg = "✅ Verificado" if r['verified'] else "⚠️ Ojo: Mucho spread entre exchanges"
            return (
                f"📊 *Análisis de {r['symbol']} ({r['name']})*\n\n"
                f"💰 Precio: {price_fmt(r['price_anchor'])}\n"
                f"🔒 Status: {v_msg}\n"
                f"⚡ Score: {r['engine_score']:.1f} | Riesgo: {r['risk']}\n"
                f"📈 Momento: 7d: {pct(r['mom_7d'])} | 30d: {pct(r['mom_30d'])}\n"
                f"💎 MarketCap: {r.get('market_cap', 0):,.0f}"
            )

    # 5. Caso: Análisis General con IA
    majors, alts = split_alts_and_majors(rows[:top_n])
    
    # Preparar paquete para la IA
    payload = json.dumps({
        "mode": mode,
        "market_stats": v_stats,
        "top_picks": [{"s": r["symbol"], "score": round(r["engine_score"],1), "v": r["verified"]} for r in rows[:10]]
    })
    
    news = get_news_summary_for_llm(6)
    
    # Traemos lo que veníamos hablando para que no sea un robot desmemoriado
    from core.brain import recent_context_text
    context = recent_context_text(state, chat_id)
    
    return llm_render_wrapped(user_text, payload, news, context)
