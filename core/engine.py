from core.market import (
    fetch_top100_market,
    split_alts_and_majors,
    rank_top
)

from core.learning import get_learning_boost


# ----------------------------------------------------
# MODE DETECTION
# ----------------------------------------------------

def detect_mode(text: str):

    t = (text or "").lower()

    if "mensual" in t:
        return "MONTHLY"

    if "diario" in t or "hoy" in t:
        return "DAILY"

    return "WEEKLY"


# ----------------------------------------------------
# STRUCTURE SCORING
# ----------------------------------------------------

def compute_engine_score(row):

    mom7 = row.get("mom_7d", 0)
    mom30 = row.get("mom_30d", 0)

    # base estructura
    base = (mom7 * 0.6) + (mom30 * 0.4)

    # learning adaptativo
    learn = get_learning_boost(row["symbol"])

    # estabilidad (evita pumps falsos)
    stability = 0
    if mom7 > 0 and mom30 > 0:
        stability = 5
    elif mom7 > 0 and mom30 < 0:
        stability = -3

    return base + stability + learn


# ----------------------------------------------------
# BUILD ANALYSIS
# ----------------------------------------------------

def build_engine_analysis(user_text: str):

    mode = detect_mode(user_text)

    market_rows = fetch_top100_market()

    enriched = []

    for r in market_rows:

        score = compute_engine_score(r)

        new_row = dict(r)
        new_row["engine_score"] = score

        enriched.append(new_row)

    # ranking final TOP 20
    ranked = sorted(
        enriched,
        key=lambda x: x["engine_score"],
        reverse=True
    )[:20]

    majors, alts = split_alts_and_majors(ranked)

    return format_report(mode, majors, alts)


# ----------------------------------------------------
# REPORT FORMATTER (LIMPIO)
# ----------------------------------------------------

def format_report(mode, majors, alts):

    lines = []

    lines.append(f"Panorama {mode}")

    if majors:
        lines.append("")
        lines.append("NO-ALTS")
        for i, r in enumerate(majors, 1):
            lines.append(
                f"{i}) {r['symbol']} | score {round(r['engine_score'],1)} | riesgo {r['risk']} | 7d {r['mom_7d']}"
            )

    if alts:
        lines.append("")
        lines.append("ALTS")
        for i, r in enumerate(alts, 1):
            lines.append(
                f"{i}) {r['symbol']} | score {round(r['engine_score'],1)} | riesgo {r['risk']} | 7d {r['mom_7d']}"
            )

    return "\n".join(lines)