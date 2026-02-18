import json
import os
import logging
import threading
import math
from typing import Dict, Any

# Importante: Importar las funciones de estado para que el puente funcione
from core.state import update_prefs, save_state

logger = logging.getLogger(__name__)

LEARN_FILE = os.getenv("LEARN_FILE_PATH", "learning_state.json")
_CACHED_STATE = None
_STATE_LOCK = threading.Lock()

def load_learning() -> Dict[str, Any]:
    """Carga el aprendizaje con Singleton Pattern para eficiencia."""
    global _CACHED_STATE
    with _STATE_LOCK:
        if _CACHED_STATE is not None:
            return _CACHED_STATE
        if not os.path.exists(LEARN_FILE):
            _CACHED_STATE = {}
            return _CACHED_STATE
        try:
            with open(LEARN_FILE, "r", encoding="utf-8") as f:
                _CACHED_STATE = json.load(f)
                return _CACHED_STATE
        except Exception as e:
            logger.error(f"❌ Error cargando JSON: {e}")
            return {}

def save_learning(state: Dict[str, Any]):
    """Guarda el estado de forma atómica."""
    try:
        with _STATE_LOCK:
            temp_file = LEARN_FILE + ".tmp"
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=4)
            os.replace(temp_file, LEARN_FILE)
    except Exception as e:
        logger.error(f"❌ Error persistiendo: {e}")

def register_user_interest(text: str):
    if not text or len(text) > 500: return
    clean_text = text.upper().replace("?", "").replace("!", "").replace(",", " ").replace("$", "")
    words = clean_text.split()
    state = load_learning()
    changed = False
    blacklist = {"HOLA", "CHAU", "INFO", "DAME", "ESTA", "BIEN", "TODO", "TOP", "COMO", "CHE"}
    
    for w in words:
        if 2 <= len(w) <= 5 and w.isalpha() and w not in blacklist:
            state[w] = state.get(w, 0) + 1
            changed = True
    if changed:
        save_learning(state)

def get_learning_boost(symbol: str) -> float:
    """Calcula el Heat Score logarítmico."""
    if not symbol: return 0.0
    state = load_learning()
    interest_count = state.get(symbol.upper(), 0)
    if interest_count <= 0: return 0.0
    boost = math.log10(interest_count + 1) * 3 
    return min(boost, 10.0)

# --- FUNCIÓN CORREGIDA (FUERA DE LA ANTERIOR Y CON SANGRÍA) ---
def apply_patch_to_session(state: dict, chat_id: int, patch: dict):
    """Función puente para compatibilidad con el engine."""
    if "prefs" in patch:
        update_prefs(patch["prefs"])
    
    if "brain" in patch:
        if "brain" not in state: 
            state["brain"] = {"sessions": {}}
        state["brain"]["sessions"][str(chat_id)] = patch["brain"]
    
    save_state(state)
