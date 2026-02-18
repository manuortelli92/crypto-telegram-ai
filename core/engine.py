import os
import json
import logging
from typing import List, Dict, Optional

# Se asume que estos módulos existen en tu carpeta core/
from core.market import (
    fetch_top100_market,
    split_alts_and_majors,
    estimate_risk,
    is_stable,
    is_gold,
)
from core.learning import get_learning_boost
from core.llm_gemini import gemini_render

logger = logging.getLogger(__name__)

def pct(x: Optional[float]) -> str:
    if x is None: return "n/a"
    try:
        return f"{float(x):+.2f}%"
    except (ValueError, TypeError):
        return "n/a"

def price_fmt(p: Optional[float]) -> str:
    if p is None: return "n/a"
    try:
        p = float(p)
        if p >= 1000: return f"${p:,.0f}"
        if p >= 1: return f"${p:,.2f}"
        if p >= 0.01: return f"${p:.4f}"
        return f"${p:.6f}"
    except (ValueError, TypeError):
        return "n/a"

def money(x: Optional[float]) -> str:
    if x is None: return "n/a"
    try:
        x = float(x)
        if x >= 1_000_000_000_000: return f"${x/1_000_000_000_000:.2f}T"
        if x >= 1_000_000_000: return f"${x/1_000_000_000:.2f}B"
        if x >= 1_000_000: return f"${x/1_000_000:.2f}M"
        return f"${x:,.0f}"
    except (ValueError, TypeError):
        return "n/a"

def detect_mode(text: str) -> str:
    t = (text or "").lower()
    if any(k in t for k in ["mensual", "mes"]): return "MENSUAL"
    if any(k in t for k in ["diario", "hoy", "24h"]): return "DIARIO"
    if any(k in t for k in ["semanal", "semana", "7d"]): return "SEMANAL"
    return "SEMANAL"

def parse_top_n(text: str, default: int = 20) -> int:
    t = (text or "").lower()
    if "top" in t:
        parts = t.replace(",", " ").split()
        for i, w in enumerate(parts):
            if w == "top" and i + 1 < len(parts) and parts[i + 1].isdigit():
                return max(10, min(50, int(parts[i + 1])))
    return default

def detect_risk_pref(text: str) -> Optional[str]:
    t = (text or "").lower()
    if any(k in t for k in ["bajo", "conserv", "low"]): return "LOW"
    if any(k in t for k in ["medio", "medium"]): return "MEDIUM"
    if any(k in t for k in ["alto", "agres", "high"]): return "HIGH"
    return None

def compute_engine_score(row: Dict) -> float:
    try:
        mom7 = float(row.get("mom_7d") or 0)
        mom30 = float(row.get("mom_30d") or 0)
        base = (mom7 * 0.65) + (mom30 * 0.35)

        consistency = 0.0
        if mom7 > 0 and mom30 > 0: consistency = 6.0
        elif mom7 < 0 and mom30 < 0: consistency = -4.0
        elif mom7 > 0 and mom30 < 0: consistency = -2.0

        dd_penalty = 0.0
        if mom30 < -50: dd_penalty = -10.0
        elif mom30 < -30: dd_penalty = -5.0

        cap = float(row.get("market_cap") or 0)
        vol = float(row.get("volume_24h") or 0)
        liq = (vol / cap * 150.0) if cap > 0 else 0
        liq = min(liq, 8.0)

        learn = float(get_learning_boost(row.get("symbol", "")) or 0)
        return base + consistency + dd_penalty + liq + learn
    except Exception:
        return 0.0

def pick_balanced(majors: List[Dict], alts: List[Dict], total: int):
    m_target = max(4, min(10, round(total * 0.35)))
    a_target = total - m_target
    majors_sel = majors[:m_target]
    alts_sel = alts[:a_target]
    # Rellenar si falta alguno
    if len(majors_sel) < m_target:
        alts_sel = (alts_sel + alts[a_target:a_target + (m_target - len(majors_sel))])[:total]
    return majors_sel, alts_sel

def raw_compact_json(mode: str, risk_pref: Optional[str], majors: List[Dict], alts: List[Dict]) -> str:
    def compact(items):
        return [{
            "symbol": r["symbol"],
            "name": r["name"],
            "score": round(float(r.get("engine_score", 0)), 1),
            "risk": r.get("risk", "MEDIUM"),
            "mom7": round(float(r.get("mom_7d", 0)), 2),
            "mom30": round(float(r.get("mom_30d", 0)), 2),
            "price": float(r.get("price", 0)),
            "mcap": float(r.get("market_cap", 0)),
        } for r in items]

    return json.dumps({
        "mode": mode,
        "risk_pref": risk_pref,
        "no_alts": compact(majors),
        "alts": compact(alts)
    }, ensure_ascii=False)

def llm_render_wrapped(user_text: str, payload_json: str, fallback_text: str) -> str:
    system = (
        "Sos un analista cripto experto de Argentina. Usás lenguaje rioplatense (che, vos, tené cuidado). "
        "No das consejo financiero. Sé directo. Usá únicamente los datos del JSON."
    )
    user = (
        f"Pedido del usuario: {user_text}\n\n"
        f"Datos del mercado: {payload_json}\n\n"
        "Respondé con un breve análisis y 5 a 8 recomendaciones claras."
    )
    try:
        out = gemini_render(system, user)
        return out if out else fallback_text
    except Exception as e:
        logger.error(f"Error en Gemini: {e}")
        return fallback_text

def build_engine_analysis(user_text: str) -> str:
    mode = detect_mode(user_text)
    top_n = parse_top_n(user_text)
    risk_pref = detect_risk_pref(user_text)

    rows = fetch_top100_market()
    # Filtro de seguridad
    rows = [r for r in rows if r.get("symbol") and not is_stable(r) and not is_gold(r)]
    
    # Búsqueda de símbolo específico
    tokens = user_text.upper().replace("?", "").split()
    symbol_found = next((r for r in rows if r["symbol"] in tokens), None)

    enriched = []
    for r in rows:
        rr = dict(r)
        rr["engine_score"] = compute_engine_score(rr)
        rr["risk"] = estimate_risk(rr)
        enriched.append(rr)
    
    enriched.sort(key=lambda x: x["engine_score"], reverse=True)

    if symbol_found:
        r = next((x for x in enriched if x["symbol"] == symbol_found["symbol"]), None)
        return (
            f"📊 *{r['symbol']} ({r['name']})*\n"
            f"💰 Precio: {price_fmt(r['price'])}\n"
            f"⚡ Score: {r['engine_score']:.1f} | Riesgo: {r['risk']}\n"
            f"📈 7d: {pct(r['mom_7d'])} | 30d: {pct(r['mom_30d'])}\n"
            f"💎 Cap: {money(r['market_cap'])}"
        )

    top = enriched[:top_n]
    majors, alts = split_alts_and_majors(top)
    majors_sel, alts_sel = pick_balanced(majors, alts, top_n)

    fallback = f"Análisis {mode} disponible. (Error de IA, mostrando básico)\n" + \
               f"Top Sugerido: {', '.join([x['symbol'] for x in majors_sel[:5]])}"

    payload = raw_compact_json(mode, risk_pref, majors_sel, alts_sel)
    return llm_render_wrapped(user_text, payload, fallback)
