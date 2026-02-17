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
from core.news import fetch_news
from core.signals import build_news_signals

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
    return default


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


def _exclude_weird_assets(row: Dict) -> bool:
    # Filtra “fondos tokenizados” y cosas no-crypto típicas que CoinGecko a veces mete en top 100
    name = (row.get("name") or "").lower()
    sym = (row.get("symbol") or "").upper()

    bad_words = [
        "treasury", "fund", "money market", "clo", "gov", "government", "bond",
        "helic", "heloc", "janus", "superstate", "anemoy", "figure",
    ]
    if any(w in name for w in bad_words):
        return True
    if sym.endswith("B") and "bond" in name:
        return True
    return False


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
    # 35% majors, 65% alts (mínimos razonables)
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


def fallback_compact(mode: str, top_n: int, majors: List[Dict], alts: List[Dict], signals: Dict) -> str:
    # Compacto y entendible: 4-6 líneas + lista corta
    lines = []
    lines.append(f"Panorama {mode} | Top {top_n}")
    if signals.get("n_items", 0) > 0:
        tags = signals.get("tag_counts", {})
        top_syms = signals.get("top_symbols", [])
        if tags:
            top_tags = ", ".join(sorted(tags.keys(), key=lambda k: tags[k], reverse=True)[:4])
            lines.append(f"Señales news: {top_tags}")
        if top_syms:
            lines.append(f"Tokens mencionados en news: {', '.join(top_syms[:6])}")

    lines.append("")
    lines.append("NO-ALTS (selección)")
    for r in majors[:6]:
        lines.append(f"- {r['symbol']} score {r['engine_score']:.1f} | 7d {pct(r['mom_7d'])} | 30d {pct(r['mom_30d'])} | {price_fmt(r['price'])}")

    lines.append("")
    lines.append("ALTS (selección)")
    for r in alts[:10]:
        lines.append(f"- {r['symbol']} score {r['engine_score']:.1f} | 7d {pct(r['mom_7d'])} | 30d {pct(r['mom_30d'])} | {price_fmt(r['price'])}")

    return "\n".join(lines)


def llm_render(user_text: str, payload_json: str, fallback_text: str) -> str:
    if not OPENAI_API_KEY:
        return fallback_text

    try:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY)
    except Exception:
        return fallback_text

    system = (
        "Sos un analista cripto prudente. Español rioplatense, claro y conversacional. "
        "No das asesoramiento financiero. "
        "No pegues listados largos. No muestres titulares. "
        "REGLA: solo podés usar datos del JSON; no inventes."
    )

    user = (
        f"Usuario dijo: {user_text}\n\n"
        f"JSON (fuente única):\n{payload_json}\n\n"
        "Respondé así:\n"
        "1) Panorama en 2-3 líneas.\n"
        "2) 6 a 10 ideas concretas (mezclá NO-ALTS y ALTS): por qué entra, riesgo, y qué invalida.\n"
        "3) Si el usuario pidió diario/semanal/mensual, adaptá el horizonte.\n"
        "4) Usá news_signals SOLO como contexto (tags y tokens mencionados), sin titulares.\n"
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
    symbol = extract_symbol(user_text)

    # Market
    rows = fetch_top100_market()

    # Filtros clave
    rows = [
        r for r in rows
        if r.get("symbol")
        and (not is_stable(r))
        and (not is_gold(r))
        and (not _exclude_weird_assets(r))
    ]

    enriched = []
    for r in rows:
        rr = dict(r)
        rr["engine_score"] = compute_engine_score(rr)
        rr["risk"] = estimate_risk(rr)
        enriched.append(rr)

    enriched.sort(key=lambda x: x["engine_score"], reverse=True)

    # Ficha por símbolo si preguntan por una moneda
    if symbol and any(k in (user_text or "").lower() for k in ["?", "como", "ves", "hoy", "seman", "mes", "diario", "mensual"]):
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

    # News signals (sin titulares)
    news = fetch_news(limit_total=40)
    signals = build_news_signals(news, max_items=8)

    payload = {
        "mode": mode,
        "no_alts": [
            {
                "symbol": r["symbol"], "name": r["name"],
                "score": round(float(r["engine_score"]), 1),
                "risk": r["risk"],
                "mom7": round(float(r["mom_7d"]), 2),
                "mom30": round(float(r["mom_30d"]), 2),
                "price": float(r["price"]),
                "mcap": float(r["market_cap"]),
                "vol24h": float(r["volume_24h"]),
            } for r in majors
        ],
        "alts": [
            {
                "symbol": r["symbol"], "name": r["name"],
                "score": round(float(r["engine_score"]), 1),
                "risk": r["risk"],
                "mom7": round(float(r["mom_7d"]), 2),
                "mom30": round(float(r["mom_30d"]), 2),
                "price": float(r["price"]),
                "mcap": float(r["market_cap"]),
                "vol24h": float(r["volume_24h"]),
            } for r in alts
        ],
        "news_signals": signals,
        "rules": {"use_only_payload": True},
    }

    payload_json = json.dumps(payload, ensure_ascii=False)
    fallback = fallback_compact(mode, top_n, majors, alts, signals)
    return llm_render(user_text, payload_json, fallback)