import os
import json
from typing import List, Dict, Optional, Tuple

from core.market import (
    fetch_top100_market,
    split_alts_and_majors,
    estimate_risk,
    is_stable,
    is_gold,
)
from core.learning import get_learning_boost
from core.sources import verify_price_multi_source
from core.memory import load_state

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()


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
    for tok in t.replace(",", " ").split():
        if tok.isdigit():
            n = int(tok)
            return max(10, min(50, n))
    if "top 10" in t:
        return 10
    if "top 20" in t:
        return 20
    if "top 30" in t:
        return 30
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


def detect_request_kind(text: str) -> str:
    t = (text or "").lower()
    if any(k in t for k in ["top", "lista", "ranking", "mostrame", "mostrá"]):
        return "LIST"
    if any(k in t for k in ["informe", "panorama", "resumen", "diario", "semanal", "mensual"]):
        return "BRIEF"
    return "CHAT"


def wants_no_memecoins(text: str) -> bool:
    t = (text or "").lower()
    return any(k in t for k in ["sin memecoin", "sin memecoins", "evita memecoin", "evita memecoins", "no memecoin", "no memecoins"])


def extract_symbol(text: str) -> Optional[str]:
    if not text:
        return None

    BLOCKED = {
        "HOLA","HOY","INFO","TOP","DAME","QUIERO","RIESGO",
        "SEMANAL","DIARIO","MENSUAL","INFORME","PANORAMA","RESUMEN",
        "PEDIDO","USER","ACTUAL","LISTA","RANKING",
        "ANALIZANDO","GRACIAS","SIN","CON","PARA","DEL","DE","LA","EL"
    }

    tokens = (
        text.replace(",", " ")
        .replace("?", " ")
        .replace("!", " ")
        .replace(":", " ")
        .replace("(", " ")
        .replace(")", " ")
        .split()
    )

    for tok in tokens:
        up = tok.upper().strip()
        if not up.isalpha():
            continue
        if len(up) < 2 or len(up) > 5:
            continue
        if up in BLOCKED:
            continue
        return up

    return None


_MEME_SYMBOLS = {
    "DOGE","SHIB","PEPE","FLOKI","BONK","WIF","BOME","POPCAT","BABYDOGE","ELON","BRETT"
}
_MEME_KEYWORDS = ["inu", "doge", "pepe", "shib", "floki", "bonk", "wif", "meme"]


def is_memecoin(row: Dict) -> bool:
    sym = (row.get("symbol") or "").upper()
    if sym in _MEME_SYMBOLS:
        return True
    name = (row.get("name") or "").lower()
    cid = (row.get("id") or "").lower()
    return any(k in name for k in _MEME_KEYWORDS) or any(k in cid for k in _MEME_KEYWORDS)


def compute_engine_score(row: Dict, prefs: Dict) -> float:
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

    anchor = float(row.get("price", 0) or 0)
    ok_sources, _used = verify_price_multi_source(anchor, row["symbol"], tolerance_pct=2.0)
    verify_bonus = min(ok_sources * 1.5, 4.5)

    # Preferencias: focus boost / avoid penalty
    focus = set((prefs.get("focus") or []))
    avoid = set((prefs.get("avoid") or []))
    sym = row["symbol"]

    pref_boost = 0.0
    if sym in focus:
        pref_boost += 6.0
    if sym in avoid:
        pref_boost -= 12.0

    # Preferencias: evitar memecoins penaliza fuerte (si por algo pasan)
    if prefs.get("avoid_memecoins") and is_memecoin(row):
        pref_boost -= 20.0

    return base + consistency + dd_penalty + liq + learn + verify_bonus + pref_boost


def pick_balanced(majors: List[Dict], alts: List[Dict], total: int) -> Tuple[List[Dict], List[Dict]]:
    m_target = max(5, min(12, round(total * 0.40)))
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


def _enrich(rows: List[Dict], prefs: Dict) -> List[Dict]:
    enriched = []
    for r in rows:
        rr = dict(r)
        rr["risk"] = estimate_risk(rr)
        anchor = float(rr.get("price", 0) or 0)
        ok_sources, used = verify_price_multi_source(anchor, rr["symbol"], tolerance_pct=2.0)
        rr["sources_ok"] = int(ok_sources)
        rr["sources_used"] = used
        rr["engine_score"] = compute_engine_score(rr, prefs)
        enriched.append(rr)
    enriched.sort(key=lambda x: x["engine_score"], reverse=True)
    return enriched


def _row_line(r: Dict, idx: int) -> str:
    return (
        f"{idx:>2}) {r['symbol']} | score {r['engine_score']:.1f} | riesgo {r['risk']} | "
        f"7d {pct(r['mom_7d'])} | 30d {pct(r['mom_30d'])} | "
        f"precio {price_fmt(r['price'])} | mcap {money(r['market_cap'])} | src_ok {r.get('sources_ok', 0)}"
    )


def _list_output(mode: str, top_n: int, majors: List[Dict], alts: List[Dict]) -> str:
    lines = [f"Panorama {mode} | Top {top_n}", "", "NO-ALTS"]
    if not majors:
        lines.append("(sin resultados en NO-ALTS)")
    else:
        for i, r in enumerate(majors, 1):
            lines.append(_row_line(r, i))

    lines += ["", "ALTS"]
    if not alts:
        lines.append("(sin resultados en ALTS)")
    else:
        for i, r in enumerate(alts, 1):
            lines.append(_row_line(r, i))

    return "\n".join(lines)


def _compact_payload(mode: str, risk_pref: Optional[str], majors: List[Dict], alts: List[Dict]) -> str:
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
                "sources_ok": int(r.get("sources_ok", 0)),
                "sources_used": r.get("sources_used", ""),
            })
        return out

    payload = {
        "mode": mode,
        "risk_pref": risk_pref,
        "no_alts": compact(majors),
        "alts": compact(alts),
        "rules": {"use_only_payload": True, "no_headlines": True, "no_notes": True},
    }
    return json.dumps(payload, ensure_ascii=False)


def _llm_render(user_text: str, payload_json: str, fallback: str) -> str:
    if not OPENAI_API_KEY:
        return fallback

    try:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY)
    except Exception:
        return fallback

    system = (
        "Sos un analista cripto prudente. Español rioplatense, claro y conversacional. "
        "No das asesoramiento financiero. "
        "PROHIBIDO: titulares/noticias, notas largas, listas gigantes. "
        "REGLA: solo podés usar datos del JSON. No inventes."
    )

    user = (
        f"Usuario: {user_text}\n\n"
        f"JSON (fuente única):\n{payload_json}\n\n"
        "Formato:\n"
        "1) 2-3 líneas de panorama.\n"
        "2) 4 a 8 ideas accionables mezclando NO-ALTS y ALTS.\n"
        "   - Cada idea: símbolo + por qué + riesgo + invalida (corto).\n"
        "3) Si el usuario pidió 'top/lista/ranking', no pegues 20 líneas: resumí y ofrecé lista completa.\n"
        "4) Si falta info, 1 pregunta.\n"
    )

    try:
        resp = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0.35,
        )
        out = (resp.choices[0].message.content or "").strip()
        return out if out else fallback
    except Exception:
        return fallback


def build_engine_analysis(user_text: str) -> str:
    st = load_state()
    prefs = (st.get("prefs") or {})

    mode = detect_mode(user_text)
    top_n = parse_top_n(user_text, default=20)
    kind = detect_request_kind(user_text)
    symbol = extract_symbol(user_text)

    # preferencia de riesgo: lo que dice el usuario en el mensaje pisa la guardada
    msg_risk = detect_risk_pref(user_text)
    risk_pref = msg_risk or prefs.get("risk")

    # memecoins: si el mensaje lo pide, pisa
    no_memecoins = wants_no_memecoins(user_text) or bool(prefs.get("avoid_memecoins"))

    rows = fetch_top100_market()

    # Fuera stables y oro siempre
    rows = [r for r in rows if r.get("symbol") and (not is_stable(r)) and (not is_gold(r))]

    # Fuera memecoins si corresponde
    if no_memecoins:
        rows = [r for r in rows if not is_memecoin(r)]

    enriched = _enrich(rows, prefs)

    # filtro de riesgo si hay preferencia explícita
    if risk_pref in {"LOW", "MEDIUM", "HIGH"}:
        enriched = [r for r in enriched if r.get("risk") == risk_pref]

    # símbolo puntual
    if symbol:
        r = next((x for x in enriched if x["symbol"] == symbol), None)
        if not r:
            return f"No encontré {symbol} en el top 100 actual."
        return (
            f"{r['symbol']} ({r['name']})\n"
            f"precio {price_fmt(r['price'])} | riesgo {r['risk']} | score {r['engine_score']:.1f}\n"
            f"7d {pct(r['mom_7d'])} | 30d {pct(r['mom_30d'])}\n"
            f"mcap {money(r['market_cap'])} | vol24h {money(r['volume_24h'])}\n"
            f"verificación: src_ok {r.get('sources_ok', 0)} ({r.get('sources_used','')})"
        )

    top = enriched[:top_n]
    majors, alts = split_alts_and_majors(top)
    majors, alts = pick_balanced(majors, alts, top_n)

    fallback_list = _list_output(mode, top_n, majors, alts)
    payload = _compact_payload(mode, risk_pref, majors, alts)

    if kind == "LIST":
        return _llm_render(user_text, payload, fallback_list)

    fallback_brief = f"Panorama {mode}. Si querés lista: 'top {top_n}'."
    return _llm_render(user_text, payload, fallback_brief)