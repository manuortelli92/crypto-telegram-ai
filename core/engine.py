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
    if "top " in t:
        # top 20 / top 30 etc
        try:
            after = t.split("top ", 1)[1].strip()
            n = int(after.split()[0])
            return max(5, min(50, n))
        except Exception:
            pass

    # si escribió un número suelto, lo tomamos como top_n (con límites)
    for tok in t.replace(",", " ").split():
        if tok.isdigit():
            n = int(tok)
            return max(5, min(50, n))

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


def _tokenize(text: str) -> List[str]:
    if not text:
        return []
    return (
        text.replace(",", " ")
        .replace("?", " ")
        .replace("!", " ")
        .replace(":", " ")
        .replace("(", " ")
        .replace(")", " ")
        .replace("/", " ")
        .replace("\\", " ")
        .split()
    )


def extract_symbol(text: str) -> Optional[str]:
    """
    FIX: evita tomar palabras del contexto (PEDIDO/CONTEXTO/etc) como si fueran tickers.
    Regla: solo 2-6 letras, alpha, y NO en blacklist. Para >=5 letras exigimos que parezca ticker real.
    """
    BLOCKED = {
        "HOLA", "HOY", "INFO", "TOP", "DAME", "QUIERO", "RIESGO",
        "SEMANAL", "DIARIO", "MENSUAL",
        "PEDIDO", "ACTUAL", "CONTEXTO", "PARAMETROS", "PARAMETROS", "PARAMS",
        "MODE", "FOCUS", "AVOID", "PREFIERO", "EVITA", "INFORME"
    }

    # allowlist chica para tickers de 5 letras que suelen existir y la gente pregunta
    ALLOW_5PLUS = {"USDT", "USDC", "DAI", "PAXG", "XAUT"}  # igual luego se filtran stables/oro

    for tok in _tokenize(text):
        up = tok.upper().strip()

        if not up.isalpha():
            continue

        if up in BLOCKED:
            continue

        if len(up) < 2 or len(up) > 6:
            continue

        # Para 5-6 letras: solo si está en allowlist (reduce falsos positivos tipo PEDIDO)
        if len(up) >= 5 and up not in ALLOW_5PLUS:
            continue

        return up

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

    learn = float(get_learning_boost(row.get("symbol", "")) or 0)

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


def raw_report(mode: str, top_n: int, majors: List[Dict], alts: List[Dict]) -> str:
    lines = []
    lines.append(f"Panorama {mode} | Top {top_n}")
    lines.append("")

    lines.append("NO-ALTS")
    if not majors:
        lines.append("(sin resultados en NO-ALTS con los filtros actuales)")
    else:
        for i, r in enumerate(majors, 1):
            lines.append(
                f"{i}) {r['symbol']} ({r['name']}) | score {r['engine_score']:.1f} | riesgo {r['risk']} | "
                f"7d {pct(r['mom_7d'])} | 30d {pct(r['mom_30d'])} | precio {price_fmt(r['price'])} | "
                f"mcap {money(r['market_cap'])} | vol24h {money(r['volume_24h'])}"
            )

    lines.append("")
    lines.append("ALTS")
    if not alts:
        lines.append("(sin resultados en ALTS con los filtros actuales)")
    else:
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
        "No das asesoramiento financiero. "
        "No incluyas titulares, RSS, ni notas largas. "
        "REGLA: solo podés usar datos dentro del JSON. No inventes."
    )

    user = (
        f"Usuario dijo: {user_text}\n\n"
        f"JSON (fuente única):\n{payload_json}\n\n"
        "Respondé:\n"
        "- 2-3 líneas de panorama.\n"
        "- 4 a 8 ideas concretas (mezclá no-alts y alts): por qué entra, riesgo, y qué invalida.\n"
        "- Si el usuario pidió 'top N', podés listar como máximo 12 items, no más.\n"
        "- Si falta info, hacé 1 pregunta corta.\n"
        "- No pegues el listado entero del fallback.\n"
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

    # FILTROS CLAVE: afuera stables y oro
    rows = [r for r in rows if r.get("symbol") and (not is_stable(r)) and (not is_gold(r))]

    enriched = []
    for r in rows:
        rr = dict(r)
        rr["engine_score"] = compute_engine_score(rr)
        rr["risk"] = estimate_risk(rr)
        enriched.append(rr)

    enriched.sort(key=lambda x: x["engine_score"], reverse=True)

    # Si preguntó por símbolo, devolvemos ficha corta (sin confundirse con "PEDIDO", etc.)
    if symbol and any(k in (user_text or "").lower() for k in ["?", "como", "ves", "hoy", "seman", "mes", "diar"]):
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

    fallback = raw_report(mode, top_n, majors, alts)
    payload = raw_compact_json(mode, risk_pref, majors, alts)

    return llm_render(user_text, payload, fallback)