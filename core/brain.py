import time
import json
import logging
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

def _now() -> float: return time.time()

def _trim(s: str, max_len: int = 800) -> str:
    s = (s or "").strip()
    return s[:max_len].rstrip() + "..." if len(s) > max_len else s

def ensure_brain(state: Any) -> Dict:
    if not isinstance(state, dict): state = {}
    if "brain" not in state: state["brain"] = {"sessions": {}}
    return state["brain"]

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
    if "facts" not in sess: sess["facts"] = []
    return sess

def add_turn(state: Dict, chat_id: int, role: str, text: str):
    sess = get_session(state, chat_id)
    sess["history"].append({"ts": _now(), "role": role, "text": _trim(text)})
    if len(sess["history"]) > 20: sess["history"] = sess["history"][-20:]

def recent_context_text(state: Dict, chat_id: int) -> str:
    sess = get_session(state, chat_id)
    lines = [f"{'Usuario' if h['role']=='user' else 'Bot'}: {h['text']}" for h in sess["history"]]
    return "\n".join(lines).strip()

def apply_patch_to_session(state: Dict, chat_id: int, user_text: str) -> Dict:
    # Nota: Aquí asumo que mantienes tus funciones detect_mode y extract_prefs_patch
    # Si no, las incluimos. Por brevedad, retorno la estructura que el engine espera:
    sess = get_session(state, chat_id)
    return {
        "mode": sess.get("last_mode", "SEMANAL"),
        "top_n": sess.get("last_top_n", 20),
        "risk_pref": sess.get("facts", {}).get("risk_pref", "Medio"),
        "avoid": sess.get("facts", {}).get("avoid", []),
        "focus": sess.get("facts", {}).get("focus", []),
        "context": recent_context_text(state, chat_id)
    }

def save_brain_state(state: Dict):
    try:
        with open("brain_state.json", "w", encoding="utf-8") as f:
            json.dump(state, f, indent=4)
    except Exception as e:
        logger.error(f"❌ Error guardando brain: {e}")
