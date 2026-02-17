import math
from typing import List, Dict, Optional

from core.market import (
    fetch_top100_market,
    split_alts_and_majors,
    estimate_risk,
    is_stable,
)

from core.learning import get_learning_boost


# ---------------------------
# Helpers de formato
# ---------------------------

def pct(x: float) -> str:
    try:
        return f"{x:+.2f}%"
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


# ---------------------------
# Parsing “natural”
# ---------------------------

def detect_mode(text: str) -> str:
    t = (text or "").lower()
    if "mensual" in t or "mes" in t:
        return "MENSUAL"
    if "diario" in t or "hoy" in t:
        return "DIARIO"
    return "SEMANAL"

def parse_top_n(text: str, default: int = 20) -> int:
    t = (text or "").lower()
    for token in t.replace(",", " ").split():
        if token.isdigit():
            n = int(token)
            return max(5, min(50, n))
    if "top 10" in t:
        return 10
    if "top 20" in t:
        return 20
    return default

def extract_symbol(text: str) -> Optional[str]:
    if not text:
        return None
    # Busca un símbolo tipo BTC / ETH / SOL
    tokens = text.replace(",", " ").replace("?", " ").replace("!", " ").split()
    for tok in tokens:
        up = tok.upper().strip()
        if 2 <= len(up) <= 6 and up.isalpha():
            return up
    return None


# ---------------------------
# Scoring “serio”
# ---------------------------

def compute_engine_score(row: Dict) -> float:
    mom7 = float(row.get("mom_7d", 0) or 0)
    mom30 = float(row.get("mom_30d", 0) or 0)

    # Estructura: balance entre corto y medio plazo
    base = (mom7 * 0.65) + (mom30 * 0.35)

    # Consistencia
    consistency = 0.0
    if mom7 > 0 and mom30 > 0:
        consistency = 6.0
    elif mom7 < 0 and mom30 < 0:
        consistency = -4.0
    elif mom7 > 0 and mom30 < 0:
        consistency = -2.0

    # Penalización por drawdown fuerte (solo por 30d)
    dd_penalty = 0.0
    if mom30 < -50:
        dd_penalty = -10.0
    elif mom30 < -30:
        dd_penalty = -5.0

    # Liquidez relativa (volumen/marketcap) como sanity check
    cap = float(row.get("market_cap", 0) or 0)
    vol = float(row.get("volume_24h", 0) or 0)
    liq = 0.0
    if cap > 0:
        ratio = vol / cap  # 0.01 = 1%
        liq = min(ratio * 150.0, 8.0)  # cap a 8

    # Aprendizaje del usuario (capado)
    learn = float(get_learning_boost(row["symbol"]) or 0)

    return base + consistency + dd_penalty + liq + learn


# ---------------------------
# Construcción de respuestas
# ---------------------------

def pick_balanced(majors: List[Dict], alts: List[Dict], total: int) -> (List[Dict], List[Dict]):
    # Queremos que SIEMPRE haya NO-ALTS primero (si existen)
    # Regla: 6 majors + 14 alts si total=20 (ajusta proporcional)
    m_target = max(3, min(8, round(total * 0.3)))
    a_target = total - m_target

    majors_sel = majors[:m_target]
    alts_sel = alts[:a_target]

    # Si faltan majors, completamos con alts; si faltan alts, completamos con majors
    if len(majors_sel) < m_target:
        need = m_target - len(majors_sel)
        alts_sel = (alts_sel + alts[a_target:a_target + need])[:total]
    if len(alts_sel) < a_target:
        need = a_target - len(alts_sel)
        majors_sel = (majors_sel + majors[m_target:m_target + need])[:total]

    return majors_sel, alts_sel

def format_list(title: str, items: List[Dict]) -> List[str]:
    lines = []
    if not items:
        return lines
    lines.append(title)
    for i, r in enumerate(items, 1):
        lines.append(
            f"{i}) {r['symbol']} ({r.get('name','')}) | score {r['engine_score']:.1f} | "
            f"riesgo {r['risk']} | 7d {pct(r['mom_7d'])} | 30d {pct(r['mom_30d'])} | "
            f"precio {price_fmt(r['price'])}"
        )
    return lines

def build_symbol_brief(rows: List[Dict], symbol: str, mode: str) -> str:
    r = next((x for x in rows if x["symbol"] == symbol), None)
    if not r:
        return f"No encontré {symbol} en el top 100 actual."

    lines = []
    lines.append(f"{symbol} ({r.get('name','')}) - {mode}")
    lines.append(f"precio: {price_fmt(r['price'])} | mcap: {money(r['market_cap'])} | vol24h: {money(r['volume_24h'])}")
    lines.append(f"momento: 7d {pct(r['mom_7d'])} | 30d {pct(r['mom_30d'])} | riesgo {r['risk']} | score {r['engine_score']:.1f}")

    # Lectura rápida
    if r["mom_7d"] > 0 and r["mom_30d"] > 0:
        lines.append("lectura: tendencia positiva con estructura favorable.")
    elif r["mom_7d"] > 0 and r["mom_30d"] < 0:
        lines.append("lectura: rebote de corto plazo dentro de estructura débil (ojo).")
    elif r["mom_7d"] < 0 and r["mom_30d"] < 0:
        lines.append("lectura: debilidad en corto y medio plazo (evitar perseguir).")
    else:
        lines.append("lectura: mixto; requiere confirmación.")

    return "\n".join(lines)

def build_engine_analysis(user_text: str) -> str:
    mode = detect_mode(user_text)
    top_n = parse_top_n(user_text, default=20)

    rows = fetch_top100_market()

    # Filtramos stables y símbolos vacíos
    rows = [r for r in rows if r.get("symbol") and not is_stable(r)]

    # Enriquecemos con score y riesgo
    enriched = []
    for r in rows:
        rr = dict(r)
        rr["engine_score"] = compute_engine_score(rr)
        rr["risk"] = estimate_risk(rr)
        enriched.append(rr)

    enriched.sort(key=lambda x: x["engine_score"], reverse=True)

    # Si el usuario preguntó por una moneda puntual, devolvemos ese brief
    sym = extract_symbol(user_text)
    if sym and (("?" in (user_text or "")) or ("btc" in (user_text or "").lower()) or ("eth" in (user_text or "").lower())):
        # Nota: si escribís "informe semanal" no entra acá porque no hay símbolo claro
        return build_symbol_brief(enriched, sym, mode)

    # Top N del universo (ya sin stables)
    top = enriched[:top_n]

    majors, alts = split_alts_and_majors(top)
    majors, alts = pick_balanced(majors, alts, top_n)

    lines = []
    lines.append(f"Panorama {mode} | Top {top_n}")

    lines.append("")
    lines.extend(format_list("NO-ALTS", majors))

    lines.append("")
    lines.extend(format_list("ALTS", alts))

    return "\n".join(lines)