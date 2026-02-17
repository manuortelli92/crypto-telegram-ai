import os
import json
import math
from typing import List, Dict, Optional

from core.market import (
    split_alts_and_majors,
    estimate_risk,
    is_stable,
    is_gold,
)

from core.learning import get_learning_boost

# NUEVO: multisource
from core.multisource import fetch_coingecko_top100, verify_prices

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()


# ================= FORMATO =================

def pct(x: float) -> str:
    try:
        return f"{float(x):+.2f}%"
    except:
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
    except:
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
    except:
        return "n/a"


# ================= PARSE =================

def detect_mode(text: str) -> str:
    t = (text or "").lower()
    if "mensual" in t or "mes" in t:
        return "MENSUAL"
    if "diario" in t or "hoy" in t:
        return "DIARIO"
    return "SEMANAL"


def parse_top_n(text: str, default: int = 20) -> int:
    t = (text or "").lower()
    for tok in t.split():
        if tok.isdigit():
            return max(5, min(50, int(tok)))
    return default


def extract_symbol(text: str) -> Optional[str]:
    if not text:
        return None
    stop = {"INFORME", "SEMANAL", "DIARIO", "MENSUAL"}
    for tok in text.replace("?", " ").split():
        up = tok.upper()
        if 2 <= len(up) <= 10 and up.isalpha() and up not in stop:
            return up
    return None


# ================= FILTRO RWA =================

FUND_WORDS = [
    "treasury","fund","anemoy","superstate","government securities",
    "clo","t-bill","bill","janus henderson","short duration",
    "ustb","heloc","figure","tokenized","rwa","bond","yield","credit"
]

def is_fund_like(row: Dict) -> bool:
    name = (row.get("name") or "").lower()
    sym = (row.get("symbol") or "").upper()
    if "_" in sym:
        return True
    if any(w in name for w in FUND_WORDS):
        return True
    return False


# ================= SCORE =================

def compute_engine_score(row: Dict) -> float:
    mom7 = float(row.get("mom_7d", 0) or 0)
    mom30 = float(row.get("mom_30d", 0) or 0)

    cap = float(row.get("market_cap", 0) or 0)
    vol = float(row.get("volume_24h", 0) or 0)

    base = (mom7 * 0.55) + (mom30 * 0.45)

    dd_penalty = 0.0
    if mom30 < -50:
        dd_penalty -= 10
    elif mom30 < -30:
        dd_penalty -= 6
    elif mom30 < -20:
        dd_penalty -= 3

    liq = 0.0
    if cap > 0:
        ratio = vol / cap
        liq = min(ratio * 120.0, 8.0)

    quality = 0.0
    if cap > 0:
        quality = min(max(math.log10(cap) - 8.5, 0.0) * 2.0, 10.0)

    anti_pump = 0.0
    if cap < 1_000_000_000 and mom7 > 20:
        anti_pump -= 8

    learn = float(get_learning_boost(row.get("symbol", "")) or 0)

    # -------- VERIFICACIÓN MULTI-SOURCE --------
    sources_ok = int(row.get("sources_ok", 0) or 0)
    spread = row.get("spread_pct")

    verify_penalty = 0.0
    if sources_ok <= 1:
        verify_penalty -= 8
    elif sources_ok == 2:
        verify_penalty -= 3

    if spread is not None and spread > 2:
        verify_penalty -= min((spread - 2) * 1.5, 8)

    return base + dd_penalty + liq + quality + anti_pump + learn + verify_penalty


# ================= SELECCIÓN =================

def pick_balanced_ranked(majors_ranked, alts_ranked, total):
    m_target = max(5, min(10, round(total * 0.40)))
    a_target = total - m_target
    return majors_ranked[:m_target], alts_ranked[:a_target]


# ================= OUTPUT =================

def raw_report(mode, top_n, majors, alts):
    lines = [f"Panorama {mode} | Top {top_n}", "", "NO-ALTS"]

    for i, r in enumerate(majors, 1):
        lines.append(
            f"{i}) {r['symbol']} ({r['name']}) | score {r['engine_score']:.1f} | riesgo {r['risk']} | "
            f"7d {pct(r['mom_7d'])} | 30d {pct(r['mom_30d'])} | precio {price_fmt(r['price'])}"
        )

    lines.append("")
    lines.append("ALTS")

    for i, r in enumerate(alts, 1):
        lines.append(
            f"{i}) {r['symbol']} ({r['name']}) | score {r['engine_score']:.1f} | riesgo {r['risk']} | "
            f"7d {pct(r['mom_7d'])} | 30d {pct(r['mom_30d'])} | precio {price_fmt(r['price'])}"
        )

    return "\n".join(lines)


# ================= ENTRYPOINT =================

def build_engine_analysis(user_text: str) -> str:

    mode = detect_mode(user_text)
    top_n = parse_top_n(user_text)

    # -------- MULTI SOURCE --------
    rows = fetch_coingecko_top100()
    rows, stats = verify_prices(rows)

    # usar precio consolidado
    for r in rows:
        if r.get("price_anchor"):
            r["price"] = r["price_anchor"]

    # filtros
    rows = [
        r for r in rows
        if r.get("symbol")
        and not is_stable(r)
        and not is_gold(r)
        and not is_fund_like(r)
    ]

    enriched = []
    for r in rows:
        rr = dict(r)
        rr["engine_score"] = compute_engine_score(rr)
        rr["risk"] = estimate_risk(rr)
        enriched.append(rr)

    symbol = extract_symbol(user_text)
    if symbol and len(user_text.split()) <= 6:
        r = next((x for x in enriched if x["symbol"] == symbol), None)
        if r:
            return (
                f"{r['symbol']} ({r['name']})\n"
                f"precio {price_fmt(r['price'])} | riesgo {r['risk']} | score {r['engine_score']:.1f}\n"
                f"7d {pct(r['mom_7d'])} | 30d {pct(r['mom_30d'])}"
            )

    majors_all, alts_all = split_alts_and_majors(enriched)

    majors_ranked = sorted(majors_all, key=lambda x: x["engine_score"], reverse=True)
    alts_ranked = sorted(alts_all, key=lambda x: x["engine_score"], reverse=True)

    majors_sel, alts_sel = pick_balanced_ranked(majors_ranked, alts_ranked, top_n)

    return raw_report(mode, top_n, majors_sel, alts_sel)