import time
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

def _now() -> float:
    return time.time()

def _trim(s: str, max_len: int = 800) -> str:
    s = (s or "").strip()
    if len(s) <= max_len:
        return s
    return s[:max_len].rstrip() + "..."

def ensure_brain(state: Dict) -> Dict:
    if "brain" not in state or not isinstance(state["brain"], dict):
        state["brain"] = {"sessions": {}, "global_prefs": {}}
    
    brain = state["brain"]
    if "sessions" not in brain: brain["sessions"] = {}
    if "global_prefs" not in brain: brain["global_prefs"] = {}
    return brain

def get_session(state: Dict, chat_id: int) -> Dict:
    brain = ensure_brain(state)
    sid = str(chat_id)
    
    if sid not in brain["sessions"] or not isinstance(brain["sessions"][sid], dict):
        brain["sessions"][sid] = {
            "history": [],        # [{"ts":..., "role":"user|bot", "text":"..."}]
            "facts": {},          # preferencias aprendidas
            "last_mode": "SEMANAL",
            "last_top_n": 20,
        }
    
    sess = brain["sessions"][sid]
    # Asegurar estructura interna
    if "history" not in sess: sess["history"] = []
    if "facts" not in sess: sess["facts"] = {}
    return sess

def add_turn(state: Dict, chat_id: int, role: str, text: str, max_turns: int = 10) -> None:
    sess = get_session(state, chat_id)
    # Guardamos el turno con un trim para no saturar la DB/Memoria
    sess["history"].append({
        "ts": _now(), 
        "role": role, 
        "text": _trim(text, 1000)
    })

    # Mantener solo los últimos X turnos (par de usuario/bot)
    if len(sess["history"]) > max_turns * 2:
        sess["history"] = sess["history"][-max_turns * 2:]

def recent_context_text(state: Dict, chat_id: int, max_turns: int = 6) -> str:
    sess = get_session(state, chat_id)
    hist = sess.get("history", [])
    if not hist:
        return ""

    last = hist[-max_turns * 2:]
    lines = []
    for h in last:
        role = "Usuario" if h.get("role") == "user" else "Bot"
        txt = (h.get("text") or "").strip()
        if txt:
            lines.append(f"{role}: {txt}")
    return "\n".join(lines).strip()

def detect_mode(text: str) -> Optional[str]:
    t = (text or "").lower()
    if any(k in t for k in ["mensual", "mes"]): return "MENSUAL"
    if any(k in t for k in ["diario", "hoy", "24h"]): return "DIARIO"
    if any(k in t for k in ["semanal", "semana", "7d"]): return "SEMANAL"
    return None

def parse_top_n(text: str) -> Optional[int]:
    t = (text or "").lower().replace(",", " ")
    # Intenta buscar un número después de la palabra 'top'
    if "top" in t:
        parts = t.split()
        for i, word in enumerate(parts):
            if word == "top" and i + 1 < len(parts) and parts[i+1].isdigit():
                return max(5, min(100, int(parts[i+1])))
    # Si no, busca cualquier número suelto
    for tok in t.split():
        if tok.isdigit():
            return max(5, min(100, int(tok)))
    return None

def extract_prefs_patch(text: str) -> Dict:
    t = (text or "").lower()
    patch: Dict = {}

    # Detección de riesgo
    if any(k in t for k in ["riesgo bajo", "conservador", "low"]): patch["risk_pref"] = "LOW"
    elif any(k in t for k in ["riesgo medio", "medium"]): patch["risk_pref"] = "MEDIUM"
    elif any(k in t for k in ["riesgo alto", "agresivo", "high"]): patch["risk_pref"] = "HIGH"

    # Detección de monedas a evitar o preferir
    def _clean_coins(raw_text: str) -> List[str]:
        # Filtra palabras que parecen símbolos de cripto
        potential = raw_text.replace(",", " ").replace(".", " ").upper().split()
        return [c for c in potential if 2 <= len(c) <= 6 and c.isalpha()]

    if "evita " in t:
        coins_text = t.split("evita ", 1)[1]
        patch["avoid"] = _clean_coins(coins_text)

    if "prefiero " in t or "me gusta " in t:
        # Intenta sacar la parte después de la palabra clave
        key = "prefiero " if "prefiero " in t else "me gusta "
        coins_text = t.split(key, 1)[1]
        patch["focus"] = _clean_coins(coins_text)

    return patch

def apply_patch_to_session(state: Dict, chat_id: int, user_text: str) -> Dict:
    sess = get_session(state, chat_id)

    # 1. Actualizar modo y cantidad si se detectan
    m = detect_mode(user_text)
    if m: sess["last_mode"] = m

    tn = parse_top_n(user_text)
    if tn: sess["last_top_n"] = tn

    # 2. Extraer y guardar nuevas preferencias
    patch = extract_prefs_patch(user_text)
    if patch:
        facts = sess["facts"]
        
        if "avoid" in patch:
            current = set(facts.get("avoid", []))
            current.update(patch["avoid"])
            facts["avoid"] = sorted(list(current))
            
        if "focus" in patch:
            current = set(facts.get("focus", []))
            current.update(patch["focus"])
            facts["focus"] = sorted(list(current))
            
        if "risk_pref" in patch:
            facts["risk_pref"] = patch["risk_pref"]

    # 3. Construir el objeto de retorno para el Engine
    return {
        "mode": sess.get("last_mode", "SEMANAL"),
        "top_n": int(sess.get("last_top_n", 20)),
        "risk_pref": sess["facts"].get("risk_pref"),
        "avoid": sess["facts"].get("avoid", []),
        "focus": sess["facts"].get("focus", []),
        "context": recent_context_text(state, chat_id)
    }
