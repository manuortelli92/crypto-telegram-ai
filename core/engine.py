import os
import json
from typing import List, Dict, Optional

from core.market import (
    fetch_top100_market,
    split_alts_and_majors,
    estimate_risk,
    is_stable,
    is_gold,
)
from core.learning import get_learning_boost
from core.llm_gemini import gemini_render


def pct(x: float) -> str:
    try:
        return f"{x:+.2f}%"
    except Exception:
        return "n/a"


def price_fmt(p: float) -> str:
    try:
        p = float(p)
        if p >= 1000:
            return f"${p:,.0f}"
        if p >= 1:
            return f"${p:,.2f}"
        if p >= 0.01:
            return f"${p:.4f}"
        return f"${p:.6f}"
    except Exception:
        return "n/a"


def money(x: float) -> str:
    try:
        x = float(x)
        if x >= 1_000_000_000_000:
            return f"${x/1_000_000_000_000:.2f}T"
        if x >= 1_000_000_000:
            return f"${x/1_000_000_000:.2f}B"
        if x >= 1_000_000:
            return f"${x/1_000_000:.2f}M"
        if x >= 1_000:
            return f"${x:,.0f}"
        return f"${x:.2f}"
    except Exception:
        return "n/a"


def detect_mode(text: str) -> str:
    t = (text or "").lower()
    if any(k in t for k in ["mensual", "mes"]):
        return "MENSUAL"
    if any(k in t for k in ["diario", "hoy", "24h"]):
        return "DIARIO"
    if any(k in t for k in ["semanal", "semana", "7d"]):
        return "SEMANAL"
    return "SEMANAL"


def parse_top_n(text: str, default: int = 20) -> int:
    t = (text or "").lower()
    if "top" in t:
        parts = t.replace(",", " ").split()
        for i, w in enumerate(parts):
            if w == "top" and i + 1 < len(parts) and parts[i + 1].isdigit():
                n = int(parts[i + 1])
                return max(10, min(50, n))
    for tok in t.replace(",", " ").split():
        if tok.isdigit():
            n = int(tok)
            return max(10, min(50, n))
    return default


def detect_risk_pref(text: str) -> Optional[str]:
    t = (text or "").lower()
    if any(k in t for k in ["bajo", "conserv", "low"]):
        return "LOW"
    if any(k in t for k in ["medio", "medium"]):
        return "MEDIUM"
    if any(k in t for k in ["alto", "agres", "high"]):
        return "HIGH"
    return None


def compute_engine_score(row: Dict) -> float:
    mom7 = float(row.get("mom_7d", 0) or 0)
    mom30 = float(row.get("mom_30d", 0) or 0)

    base = (mom7 * 0.65) + (mom30 * 0.35)

    consistency = 0.0
    if mom7 > 0 and mom30 > 0:
        consistency = 6.0
    elif mom7 < 0 and mom30 < 0:
        consistency = -4.0
    elif mom7 > 0 and mom30 < 0:
        consistency = -2.0

    dd_penalty = 0.0
    if mom30 < -50:
        dd_penalty = -10.0
    elif mom30 < -30:
        dd_penalty = -5.0

    cap = float(row.get("market_cap", 0) or 0)
    vol = float(row.get("volume_24h", 0) or 0)
    liq = 0.0
    if cap > 0:
        ratio = vol / cap
        liq = min(ratio * 150.0, 8.0)

    learn = float(get_learning_boost(row["symbol"]) or 0)

    return base + consistency + dd_penalty + liq + learn


def pick_balanced(majors: List[Dict], alts: List[Dict], total: int):
    m_target = max(4, min(10, round(total * 0.35)))
    a_target = total - m_target

    majors_sel = majors[:m_target]
    alts_sel = alts[:a_target]

    if len(majors_sel) < m_target:
        need = m_target - len(majors_sel)
        alts_sel = (alts_sel + alts[a_target:a_target + need])[:total]

    if len(alts_sel) < a_target:
        need = a_target - len(alts_sel)
        majors_sel = (majors_sel + majors[m_target:m_target + need])[:total]

    return majors_sel, alts_sel


def raw_compact_json(mode: str, risk_pref: Optional[str], majors: List[Dict], alts: List[Dict]) -> str:
    def compact(items):
        out = []
        for r in items:
            out.append({
                "symbol": r["symbol"],
                "name": r["name"],
                "score": round(float(r["engine_score"]), 1),
                "risk": r["risk"],
                "mom7": round(float(r["mom_7d"]), 2),
                "mom30": round(float(r["mom_30d"]), 2),
                "price": float(r["price"]),
                "mcap": float(r["market_cap"]),
                "vol24h": float(r["volume_24h"]),
            })
        return out

    payload = {
        "mode": mode,
        "risk_pref": risk_pref,
        "no_alts": compact(majors),
        "alts": compact(alts),
        "rules": {"use_only_payload": True},
    }
    return json.dumps(payload, ensure_ascii=False)


def llm_render(user_text: str, payload_json: str, fallback_text: str) -> str:
    system = (
        "Sos un analista cripto prudente. Español rioplatense, claro y conversacional. "
        "No das asesoramiento financiero. No uses titulares ni 'notas' largas. "
        "Regla estricta: solo podés usar datos dentro del JSON; no inventes."
    )

    user = (
        f"Usuario dijo: {user_text}\n\n"
        f"JSON (fuente única):\n{payload_json}\n\n"
        "Formato de respuesta:\n"
        "1) 2-3 líneas de panorama.\n"
        "2) 5 a 8 ideas concretas (mezclá no-alts y alts): por qué, riesgo, e invalida.\n"
        "3) Si falta info, 1 pregunta corta.\n"
        "Prohibido: listar top completo, titulares, notas largas.\n"
    )

    out = gemini_render(system, user)
    return out if out else fallback_text


def _extract_symbol_strict(user_text: str, known_symbols: set) -> Optional[str]:
    """
    Evita falsos positivos (PEDIDO/USER/etc).
    Solo devuelve símbolo si está en el set real del Top100.
    """
    if not user_text:
        return None

    tokens = user_text.replace(",", " ").replace("?", " ").replace("!", " ").split()
    candidates = []
    for tok in tokens:
        w = tok.strip().upper()
        if w.startswith("$"):
            w = w[1:]
        if 2 <= len(w) <= 6 and w.isalpha():
            candidates.append(w)

    for c in candidates:
        if c in known_symbols:
            return c
    return None


def build_engine_analysis(user_text: str) -> str:
    mode = detect_mode(user_text)
    top_n = parse_top_n(user_text, default=20)
    risk_pref = detect_risk_pref(user_text)

    rows = fetch_top100_market()

    # filtros: afuera stables y oro
    rows = [r for r in rows if r.get("symbol") and (not is_stable(r)) and (not is_gold(r))]

    known = {r["symbol"] for r in rows if r.get("symbol")}
    symbol = _extract_symbol_strict(user_text, known)

    enriched = []
    for r in rows:
        rr = dict(r)
        rr["engine_score"] = compute_engine_score(rr)
        rr["risk"] = estimate_risk(rr)
        enriched.append(rr)

    enriched.sort(key=lambda x: x["engine_score"], reverse=True)

    # pregunta por símbolo -> ficha corta
    if symbol:
        r = next((x for x in enriched if x["symbol"] == symbol), None)
        if not r:
            return f"No encontré {symbol} en el top 100 actual."
        return (
            f"{r['symbol']} ({r['name']})\n"
            f"precio {price_fmt(r['price'])} | riesgo {r['risk']} | score {r['engine_score']:.1f}\n"
            f"7d {pct(r['mom_7d'])} | 30d {pct(r['mom_30d'])}\n"
            f"mcap {money(r['market_cap'])} | vol24h {money(r['volume_24h'])}"
        )

    top = enriched[:top_n]
    majors, alts = split_alts_and_majors(top)
    majors, alts = pick_balanced(majors, alts, top_n)

    # fallback corto (si no hay Gemini o falla)
    fallback = (
        f"Panorama {mode} | Top {top_n}\n\n"
        f"NO-ALTS: {', '.join([x['symbol'] for x in majors[:8]])}\n"
        f"ALTS: {', '.join([x['symbol'] for x in alts[:12]])}\n"
        "Si querés: 'dame detalles de SOL' o 'top 30 riesgo medio'."
    )

    payload = raw_compact_json(mode, risk_pref, majors, alts)
    return llm_render(user_text, payload, fallback)