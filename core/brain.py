import time
import json
import os
import logging
import threading
from typing import Dict, List, Optional, Any

# Configuración del logger
logger = logging.getLogger(__name__)
_BRAIN_LOCK = threading.Lock()

def _now() -> float:
    return time.time()

def _trim(s: str, max_len: int = 800) -> str:
    s = (s or "").strip()
    if len(s) <= max_len: return s
    return s[:max_len].rstrip() + "..."

def ensure_brain(state: Any) -> Dict:
    if not isinstance(state, dict):
        state = {}
    if "brain" not in state or not isinstance(state["brain"], dict):
        state["brain"] = {"sessions": {}, "global_prefs": {}}
    brain = state["brain"]
    if "sessions" not in brain: brain["sessions"] = {}
    if "global_prefs" not in brain: brain["global_prefs"] = {}
    return brain

def get_session(state: Dict, chat_id: int) -> Dict:
    brain = ensure_brain(state)
    sid = str(chat_id)
    if sid not in brain["sessions"]:
        brain["sessions"][sid] = {
            "history": [], "facts": {}, "last_mode": "SEMANAL",
            "last_top_n": 20, "created_at": _now()
        }
    sess = brain["sessions"][sid]
    if "history" not in sess: sess["history"] = []
    if "facts" not in sess: sess["facts"] = {}
    return sess

def add_turn(state: Dict, chat_id: int, role: str, text: str, max_turns: int = 10) -> None:
    try:
        sess = get_session(state, chat_id)
        sess["history"].append({"ts": _now(), "role": role, "text": _trim(text, 1000)})
        if len(sess["history"]) > max_turns * 2:
            sess["history"] = sess["history"][-max_turns * 2:]
    except Exception as e:
        logger.error(f"❌ Error al añadir turno: {e}")

def recent_context_text(state: Dict, chat_id: int, max_turns: int = 6) -> str:
    sess = get_session(state, chat_id)
    hist = sess.get("history", [])
    if not hist: return ""
    lines = []
    for h in hist[-max_turns * 2:]:
        role = "Usuario" if h.get("role") == "user" else "Bot"
        lines.append(f"{role}: {h.get('text', '').strip()}")
    return "\n".join(lines).strip()

def detect_mode(text: str) -> Optional[str]:
    t = (text or "").lower()
    if any(k in t for k in ["mensual", "mes"]): return "MENSUAL"
    if any(k in t for k in ["diario", "hoy", "24h"]): return "DIARIO"
    if any(k in t for k in ["semanal", "semana", "7d"]): return "SEMANAL"
    return None

def parse_top_n(text: str) -> Optional[int]:
    t = (text or "").lower().replace(",", " ")
    if "top" in t:
        parts = t.split()
        for i, word in enumerate(parts):
            if word == "top" and i + 1 < len(parts) and parts[i+1].isdigit():
                return max(5, min(100, int(parts[i+1])))
    return None

def extract_prefs_patch(text: str) -> Dict:
    t = (text or "").lower()
    patch: Dict = {}
    if any(k in t for k in ["riesgo bajo", "conservador"]): patch["risk_pref"] = "LOW"
    elif any(k in t for k in ["riesgo alto", "agresivo"]): patch["risk_pref"] = "HIGH"

    def _clean_coins(raw_text: str) -> List[str]:
        return [c for c in raw_text.upper().replace(","," ").split() if 2 <= len(c) <= 6 and c.isalpha()]

    for key in ["evita ", "sacame ", "sin "]:
        if key in t: patch["avoid"] = _clean_coins(t.split(key, 1)[1]); break
    for key in ["prefiero ", "foco en "]:
        if key in t: patch["focus"] = _clean_coins(t.split(key, 1)[1]); break
    return patch

def apply_patch_to_session(state: Dict, chat_id: int, user_text: str) -> Dict:
    try:
        sess = get_session(state, chat_id)
        m = detect_mode(user_text); 
        if m: sess["last_mode"] = m
        tn = parse_top_n(user_text); 
        if tn: sess["last_top_n"] = tn
        
        patch = extract_prefs_patch(user_text)
        if patch:
            facts = sess["facts"]
            for key in ["avoid", "focus"]:
                if key in patch:
                    current = set(facts.get(key, []))
                    current.update(patch[key])
                    facts[key] = sorted(list(current))
            if "risk_pref" in patch: facts["risk_pref"] = patch["risk_pref"]

        return {
            "mode": sess.get("last_mode", "SEMANAL"),
            "top_n": int(sess.get("last_top_n", 20)),
            "risk_pref": sess["facts"].get("risk_pref"),
            "avoid": sess["facts"].get("avoid", []),
            "focus": sess["facts"].get("focus", []),
            "context": recent_context_text(state, chat_id)
        }
    except Exception as e:
        logger.error(f"❌ Error crítico en apply_patch: {e}")
        return {"mode": "SEMANAL", "top_n": 20, "risk_pref": None, "avoid": [], "focus": [], "context": ""}

def save_brain_state(state: Dict):
    """Guarda el estado del cerebro en un archivo para persistencia en Railway."""
    try:
        with _BRAIN_LOCK:
            with open("brain_state.json", "w", encoding="utf-8") as f:
                json.dump(state, f, indent=4)
    except Exception as e:
        logger.error(f"❌ Error persistiendo brain: {e}")
