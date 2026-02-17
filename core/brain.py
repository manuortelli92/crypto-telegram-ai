import time
from typing import Dict, List, Optional


def _now() -> float:
    return time.time()


def _trim(s: str, max_len: int = 800) -> str:
    s = (s or "").strip()
    if len(s) <= max_len:
        return s
    return s[:max_len].rstrip() + "..."


def ensure_brain(state: Dict) -> Dict:
    brain = state.get("brain")
    if not isinstance(brain, dict):
        brain = {"sessions": {}, "global_prefs": {}}
        state["brain"] = brain
    if "sessions" not in brain or not isinstance(brain["sessions"], dict):
        brain["sessions"] = {}
    if "global_prefs" not in brain or not isinstance(brain["global_prefs"], dict):
        brain["global_prefs"] = {}
    return brain


def get_session(state: Dict, chat_id: int) -> Dict:
    brain = ensure_brain(state)
    sid = str(chat_id)
    sess = brain["sessions"].get(sid)
    if not isinstance(sess, dict):
        sess = {
            "history": [],        # [{"ts":..., "role":"user|bot", "text":"..."}]
            "facts": {},          # preferencias aprendidas del chat
            "last_mode": "SEMANAL",
            "last_top_n": 20,
        }
        brain["sessions"][sid] = sess
    if "history" not in sess or not isinstance(sess["history"], list):
        sess["history"] = []
    if "facts" not in sess or not isinstance(sess["facts"], dict):
        sess["facts"] = {}
    return sess


def add_turn(state: Dict, chat_id: int, role: str, text: str, max_turns: int = 10) -> None:
    sess = get_session(state, chat_id)
    sess["history"].append({"ts": _now(), "role": role, "text": _trim(text, 1200)})

    # recorte por cantidad
    if len(sess["history"]) > max_turns * 2:
        sess["history"] = sess["history"][-max_turns * 2 :]


def recent_context_text(state: Dict, chat_id: int, max_turns: int = 6) -> str:
    """
    Devuelve contexto corto estilo chat:
    user: ...
    bot: ...
    """
    sess = get_session(state, chat_id)
    hist = sess.get("history", [])
    if not hist:
        return ""

    last = hist[-max_turns * 2 :]
    lines = []
    for h in last:
        role = "user" if h.get("role") == "user" else "bot"
        txt = (h.get("text") or "").strip()
        if txt:
            lines.append(f"{role}: {txt}")
    return "\n".join(lines).strip()


def detect_mode(text: str) -> Optional[str]:
    t = (text or "").lower()
    if "mensual" in t or "mes" in t:
        return "MENSUAL"
    if "diario" in t or "hoy" in t or "24h" in t:
        return "DIARIO"
    if "semanal" in t or "semana" in t or "7d" in t:
        return "SEMANAL"
    return None


def parse_top_n(text: str) -> Optional[int]:
    t = (text or "").lower().replace(",", " ")
    for tok in t.split():
        if tok.isdigit():
            n = int(tok)
            return max(10, min(50, n))
    if "top 10" in t:
        return 10
    if "top 20" in t:
        return 20
    return None


def extract_prefs_patch(text: str) -> Dict:
    """
    Aprende preferencias del usuario, simple y robusto.
    """
    t = (text or "").lower()
    patch: Dict = {}

    if any(k in t for k in ["riesgo bajo", "conservador", "low risk", "low"]):
        patch["risk_pref"] = "LOW"
    if any(k in t for k in ["riesgo medio", "medium"]):
        patch["risk_pref"] = "MEDIUM"
    if any(k in t for k in ["riesgo alto", "agresivo", "high risk", "high"]):
        patch["risk_pref"] = "HIGH"

    if "evita " in t:
        part = t.split("evita ", 1)[1]
        coins = part.replace(",", " ").upper().split()
        patch["avoid"] = list({c for c in coins if 2 <= len(c) <= 10 and c.isalpha()})

    if "prefiero " in t:
        part = t.split("prefiero ", 1)[1]
        coins = part.replace(",", " ").upper().split()
        patch["focus"] = list({c for c in coins if 2 <= len(c) <= 10 and c.isalpha()})

    return patch


def apply_patch_to_session(state: Dict, chat_id: int, user_text: str) -> Dict:
    """
    Actualiza last_mode / last_top_n y preferencias del chat.
    Devuelve un dict 'brain_prefs' para pasar al engine.
    """
    sess = get_session(state, chat_id)

    m = detect_mode(user_text)
    if m:
        sess["last_mode"] = m

    tn = parse_top_n(user_text)
    if tn:
        sess["last_top_n"] = tn

    patch = extract_prefs_patch(user_text)
    if patch:
        facts = sess["facts"]
        # merge de avoid/focus como sets
        if "avoid" in patch:
            old = set(facts.get("avoid", []) or [])
            old.update(patch["avoid"])
            facts["avoid"] = sorted(old)
        if "focus" in patch:
            old = set(facts.get("focus", []) or [])
            old.update(patch["focus"])
            facts["focus"] = sorted(old)
        if "risk_pref" in patch:
            facts["risk_pref"] = patch["risk_pref"]

    brain_prefs = {
        "mode": sess.get("last_mode", "SEMANAL"),
        "top_n": int(sess.get("last_top_n", 20) or 20),
        "risk_pref": (sess.get("facts") or {}).get("risk_pref"),
        "avoid": (sess.get("facts") or {}).get("avoid", []) or [],
        "focus": (sess.get("facts") or {}).get("focus", []) or [],
    }
    return brain_prefs