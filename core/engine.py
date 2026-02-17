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
        return "Entrada: esperar o DCA chico."
    if mom30 > 0 and mom7 > 0:
        return "Entrada: DCA o agregar en confirmacion."
    if risk == "HIGH":
        return "Entrada: tamano chico + DCA."
    return "Entrada: DCA (2-3 compras)."

def build_structured_brief(prefs: Dict) -> str:

    mkt = get_ranked_market(prefs)
    news = get_news(max_total=8)

    lines = []

    lines.append("WEEKLY BRIEF")
    lines.append(f"UTC {mkt['generated_utc']}")
    lines.append("")

    top = mkt.get("top", [])[: int(prefs.get("max_picks") or 3)]

    for i, r in enumerate(top, 1):
        lines.append(f"{i}) {r['name']} ({r['symbol']})")
        lines.append(f"Score {r['score']:.1f} | Risk {r['risk']} | Conf {r['confidence']}")
        lines.append(f"Mom 7d {fmt_pct(r['mom_7d'])} | 30d {fmt_pct(r['mom_30d'])}")
        lines.append(_entry_hint(r['risk'], r['mom_7d'], r['mom_30d']))
        lines.append("")

    if news:
        lines.append("Noticias:")
        for n in news[:5]:
            lines.append(f"- [{n.get('source')}] {n.get('title')}")

    return "\n".join(lines)

def openai_chat(system: str, user: str) -> str:

    url = "https://api.openai.com/v1/chat/completions"

    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": OPENAI_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user}
        ],
        "temperature": 0.4
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
        "Sos un analista crypto que habla SIEMPRE en espanol. "
        "Das opciones, no ordenes."
    )

    user = (
        f"Preferencias: {prefs}\n"
        f"Mensaje usuario: {user_message}\n\n"
        f"Brief base:\n{structured}"
    )

    return openai_chat(system, user)