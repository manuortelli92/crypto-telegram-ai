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

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()


# --------------------- FORMATO ---------------------

def pct(x: float) -> str:
    try:
        return f"{float(x):+.2f}%"
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


# --------------------- PARSE ---------------------

def detect_mode(text: str) -> str:
    t = (text or "").lower()
    if "mensual" in t or "mes" in t:
        return "MENSUAL"
    if "diario" in t or "hoy" in t or "24h" in t:
        return "DIARIO"
    if "semanal" in t or "semana" in t or "7d" in t:
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
    stop = {"HOLA", "HOY", "INFO", "TOP", "DAME", "QUIERO", "RIESGO", "SEMANAL", "DIARIO", "MENSUAL", "INFORME"}
    for tok in tokens:
        up = tok.upper().strip()
        if 2 <= len(up) <= 6 and up.isalpha() and up not in stop:
            return up
    return None


# --------------------- FILTROS EXTRA (RWA/FUNDS) ---------------------

FUND_WORDS = [
    "treasury", "fund", "anemoy", "superstate", "government securities", "clo", "t-bill", "bill",
    "janus henderson", "short duration", "ustb"
]

def is_fund_like(row: Dict) -> bool:
    name = (row.get("name") or "").lower()
    sym = (row.get("symbol") or "").lower()
    if any(w in name for w in FUND_WORDS):
        return True
    if any(w in sym for w in ["jtrsy", "jaaa", "ustb"]):
        return True
    return False


# --------------------- SCORE ---------------------

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

    learn = float(get_learning_boost(row.get("symbol", "")) or 0)

    return base + consistency + dd_penalty + liq + learn


# --------------------- SELECCIÓN BALANCEADA REAL ---------------------

def pick_balanced_ranked(majors_ranked: List[Dict], alts_ranked: List[Dict], total: int):
    m_target = max(5, min(10, round(total * 0.40)))  # un poco más de majors
    a_target = total - m_target

    majors_sel = majors_ranked[:m_target]
    alts_sel = alts_ranked[:a_target]

    # completar si falta alguno
    if len(majors_sel) < m_target:
        need = m_target - len(majors_sel)
        alts_sel = (alts_sel + alts_ranked[a_target:a_target + need])[:total]

    if len(alts_sel) < a_target:
        need = a_target - len(alts_sel)
        majors_sel = (majors_sel + majors_ranked[m_target:m_target + need])[:total]

    return majors_sel, alts_sel


# --------------------- OUTPUT ---------------------

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
                "symbol": r.get("symbol"),
                "name": r.get("name"),
                "score": round(float(r.get("engine_score", 0)), 1),
                "risk": r.get("risk"),
                "mom7": round(float(r.get("mom_7d", 0)), 2),
                "mom30": round(float(r.get("mom_30d", 0)), 2),
                "price": float(r.get("price", 0)),
                "mcap": float(r.get("market_cap", 0)),
                "vol24h": float(r.get("volume_24h", 0)),
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
    if not OPENAI_API_KEY:
        return fallback_text

    try:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY)
    except Exception:
        return fallback_text

    system = (
        "Sos un analista cripto prudente. Escribís en español rioplatense, claro y conversacional. "
        "No das asesoramiento financiero. No uses titulares ni notas largas. "
        "REGLA: solo podés usar datos dentro del JSON. No inventes."
    )

    user = (
        f"Usuario dijo: {user_text}\n\n"
        f"JSON (fuente única):\n{payload_json}\n\n"
        "Respondé:\n"
        "- 2-3 líneas de panorama.\n"
        "- 3 a 6 ideas concretas (mezclá no-alts y alts): por qué entra, riesgo, y qué invalida.\n"
        "- Si falta info, hacé 1 pregunta corta.\n"
        "- No pegues el listado entero.\n"
    )

    try:
        resp = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0.35,
        )
        out = resp.choices[0].message.content.strip()
        return out if out else fallback_text
    except Exception:
        return fallback_text


def build_engine_analysis(user_text: str) -> str:
    mode = detect_mode(user_text)
    top_n = parse_top_n(user_text, default=20)
    risk_pref = detect_risk_pref(user_text)
    symbol = extract_symbol(user_text)

    rows = fetch_top100_market()

    # filtros: stables, oro, y funds/treasuries tokenizados
    rows = [
        r for r in rows
        if r.get("symbol") and (not is_stable(r)) and (not is_gold(r)) and (not is_fund_like(r))
    ]

    enriched = []
    for r in rows:
        rr = dict(r)
        rr["engine_score"] = compute_engine_score(rr)
        rr["risk"] = estimate_risk(rr)
        enriched.append(rr)

    # ficha corta: solo si mensaje corto y no pide informe
    t = (user_text or "").lower()
    if symbol and ("informe" not in t) and (len((user_text or "").split()) <= 6):
        r = next((x for x in enriched if x.get("symbol") == symbol), None)
        if not r:
            return f"No encontré {symbol} en el top 100 actual."
        return (
            f"{r['symbol']} ({r['name']})\n"
            f"precio {price_fmt(r['price'])} | riesgo {r['risk']} | score {r['engine_score']:.1f}\n"
            f"7d {pct(r['mom_7d'])} | 30d {pct(r['mom_30d'])}\n"
            f"mcap {money(r['market_cap'])} | vol24h {money(r['volume_24h'])}"
        )

    # Ranking separado: majors y alts (así NO-ALTS no depende del top score)
    majors_all, alts_all = split_alts_and_majors(enriched)

    majors_ranked = sorted(majors_all, key=lambda x: x["engine_score"], reverse=True)
    alts_ranked = sorted(alts_all, key=lambda x: x["engine_score"], reverse=True)

    majors_sel, alts_sel = pick_balanced_ranked(majors_ranked, alts_ranked, top_n)

    fallback = raw_report(mode, top_n, majors_sel, alts_sel)
    payload = raw_compact_json(mode, risk_pref, majors_sel, alts_sel)

    return llm_render(user_text, payload, fallback)