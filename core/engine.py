import os
import json
from typing import Dict
import requests

from core.market import get_ranked_market, fmt_pct
from core.news import get_news

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()

def _entry_hint(risk: str, mom7: float, mom30: float) -> str:
    if mom30 < -0.10 and mom7 > 0:
        return "Entrada: escalonada (3 compras). Evitar full size."
    if mom30 < -0.10 and mom7 <= 0:
        return "Entrada: esperar o DCA chico. Tendencia aun debil."
    if mom30 > 0 and mom7 > 0:
        return "Entrada: DCA o agregar en confirmacion. Mantener plan."
    if risk == "HIGH":
        return "Entrada: tamano chico + DCA."
    return "Entrada: DCA (2-3 compras)."

def build_structured_brief(prefs: Dict) -> str:
    mkt = get_ranked_market(prefs)
    news = get_news(max_total=8)

    lines = []
    lines.append("WEEKLY BRIEF (multi-source)")
    lines.append(f"UTC {mkt['generated_utc']} | timeframe {mkt['timeframe']} | tol {int(mkt['tol']*100)}%")
    lines.append("")
    lines.append("Opciones (vos decidis):")

    top = mkt.get("top", [])[: int(prefs.get("max_picks") or 3)]
    for i, r in enumerate(top, 1):
        lines.append(f"{i}) {r['name']} ({r['symbol']})")
        lines.append(f"   Score {r['score']:.1f} | Risk {r['risk']} | Conf {r['confidence']}/100 | SourcesOK {r['sources_ok']}")
        lines.append(f"   Mom 7d {fmt_pct(r['mom_7d'])} | 30d {fmt_pct(r['mom_30d'])}")
        lines.append(f"   {_entry_hint(r['risk'], r['mom_7d'], r['mom_30d'])}")
        lines.append(f"   Fuentes: {', '.join(r['sources_used']) if r['sources_used'] else 'n/a'}")
        lines.append("")

    if news:
        lines.append("Contexto (RSS):")
        for n in news[:6]:
            lines.append(f"- [{n.get('source')}] {n.get('title')}")

    lines.append("")
    lines.append("Checklist:")
    lines.append("- Defini monto, horizonte, max perdida, y entrada escalonada.")
    lines.append("- Si Risk HIGH: asumir swings grandes, evitar apalancamiento.")
    lines.append("- Esto es informativo, no asesoramiento financiero.")
    return "\n".join(lines)

def _openai_chat(system: str, user: str) -> str:
    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": OPENAI_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.4,
    }
    r = requests.post(url, headers=headers, data=json.dumps(payload), timeout=45)
    r.raise_for_status()
    j = r.json()
    return j["choices"][0]["message"]["content"]

def build_ai_brief(prefs: Dict, user_message: str = "") -> str:
    structured = build_structured_brief(prefs)

    if not OPENAI_API_KEY:
        return structured

   system = (
    "Sos un analista crypto profesional que habla siempre en ESPANOL. "
    "Nunca respondas en ingles. "
    "Das opciones y escenarios, no ordenes ni promesas. "
    "Tu estilo es claro, humano y directo. "
    "Explicas riesgo primero y evitas hype."
)
    user = (
        "Transforma este brief estructurado (con datos verificados multi-fuente) en un mensaje mas humano en espanol con:\n"
        "1) panorama en 2-3 lineas\n"
        "2) top 3 ideas (por que, riesgo, entrada sugerida)\n"
        "3) que invalidaria cada idea\n"
        "4) preguntas cortas si falta info\n\n"
        f"Preferencias: {prefs}\n\n"
        f"Mensaje del usuario: {user_message}\n\n"
        f"Brief estructurado:\n{structured}"
    )
    return _openai_chat(system, user)