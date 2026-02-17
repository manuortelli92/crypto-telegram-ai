import os
import json
from typing import List, Dict, Optional

from core.market import fetch_top100_market, split_alts_and_majors, estimate_risk, is_stable
from core.learning import get_learning_boost

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()


# ---------------------------
# Helpers formato
# ---------------------------

def pct(x: float) -> str:
    try:
        return f"{x:+.2f}%"
    except Exception:
        return "n/a"

def price_fmt(p: float) -> str:
    try:
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


# ---------------------------
# Parsing natural
# ---------------------------

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
    for tok in t.replace(",", " ").split():
        if tok.isdigit():
            n = int(tok)
            return max(5, min(50, n))
    if "top 10" in t:
        return 10
    if "top 20" in t:
        return 20
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

def extract_symbol(text: str) -> Optional[str]:
    if not text:
        return None
    tokens = text.replace(",", " ").replace("?", " ").replace("!", " ").split()
    for tok in tokens:
        up = tok.upper().strip()
        if 2 <= len(up) <= 6 and up.isalpha():
            if up in {"HOLA", "HOY", "INFO", "TOP", "DAME", "QUIERO", "RIESGO"}:
                continue
            return up
    return None


# ---------------------------
# Scoring (mismo criterio)
# ---------------------------

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


# ---------------------------
# Selección balanceada
# ---------------------------

def pick_balanced(majors: List[Dict], alts: List[Dict], total: int):
    m_target = max(3, min(10, round(total * 0.35)))
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


# ---------------------------
# Raw report (la “verdad”)
# ---------------------------

def raw_report(mode: str, top_n: int, majors: List[Dict], alts: List[Dict]) -> str:
    lines = []
    lines.append(f"Panorama {mode} | Top {top_n}")
    lines.append("")
    lines.append("NO-ALTS")
    for i, r in enumerate(majors, 1):
        lines.append(
            f"{i}) {r['symbol']} ({r['name']}) | score {r['engine_score']:.1f} | riesgo {r['risk']} | "
            f"7d {pct(r['mom_7d'])} | 30d {pct(r['mom_30d'])} | precio {price_fmt(r['price'])} | "
            f"mcap {money(r['market_cap'])} | vol24h {money(r['volume_24h'])}"
        )
    lines.append("")
    lines.append("ALTS")
    for i, r in enumerate(alts, 1):
        lines.append(
            f"{i}) {r['symbol']} ({r['name']}) | score {r['engine_score']:.1f} | riesgo {r['risk']} | "
            f"7d {pct(r['mom_7d'])} | 30d {pct(r['mom_30d'])} | precio {price_fmt(r['price'])} | "
            f"mcap {money(r['market_cap'])} | vol24h {money(r['volume_24h'])}"
        )
    return "\n".join(lines)

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
        "rules": {
            "no_invent": True,
            "use_only_payload": True,
        }
    }
    return json.dumps(payload, ensure_ascii=False)


# ---------------------------
# LLM layer (solo redacta)
# ---------------------------

def llm_render(user_text: str, payload_json: str, payload_text: str) -> str:
    if not OPENAI_API_KEY:
        return payload_text

    try:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY)
    except Exception:
        return payload_text

    system = (
        "Sos un analista cripto prudente. Escribís en español rioplatense, claro, directo y conversacional. "
        "No das asesoramiento financiero. No uses titulares ni notas largas. "
        "REGLA: Solo podés usar datos dentro del JSON provisto. No inventes."
    )

    user = (
        f"Usuario dijo: {user_text}\n\n"
        f"JSON de datos (fuente única de verdad):\n{payload_json}\n\n"
        "Tarea:\n"
        "- Respondé como chat fluido.\n"
        "- 2-3 líneas de panorama.\n"
        "- 3 a 6 ideas concretas (mezclá no-alts y alts), cada una con: por qué entra, riesgo, y qué invalidaría.\n"
        "- Si falta info (monto, horizonte, riesgo), hacé 1 pregunta corta.\n"
        "- No repitas todas las líneas del listado, seleccioná lo importante.\n"
    )

    try:
        resp = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0.35,
        )
        out = resp.choices[0].message.content.strip()
        return out if out else payload_text
    except Exception:
        return payload_text


# ---------------------------
# Entry
# ---------------------------

def build_engine_analysis(user_text: str) -> str:
    mode = detect_mode(user_text)
    top_n = parse_top_n(user_text, default=20)
    risk_pref = detect_risk_pref(user_text)
    symbol = extract_symbol(user_text)

    rows = fetch_top100_market()
    rows = [r for r in rows if r.get("symbol") and not is_stable(r)]

    enriched = []
    for r in rows:
        rr = dict(r)
        rr["engine_score"] = compute_engine_score(rr)
        rr["risk"] = estimate_risk(rr)
        enriched.append(rr)

    enriched.sort(key=lambda x: x["engine_score"], reverse=True)

    # Si pregunta por símbolo, devolvemos mini-brief sin LLM (datos directos)
    if symbol and any(k in (user_text or "").lower() for k in ["?", "como", "ves", "hoy", "seman", "mes"]):
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

    text = raw_report(mode, top_n, majors, alts)
    payload = raw_compact_json(mode, risk_pref, majors, alts)

    # IA usa el MISMO payload del engine clásico (misma info, misma selección)
    return llm_render(user_text, payload, text)