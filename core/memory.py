import json
import os
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# En Railway, si no usas un Volume persistente, los cambios en archivos se pierden al reiniciar.
# Asegurate de que la carpeta 'core' exista.
STATE_PATH = os.getenv("STATE_PATH", "core/state.json")

def _default_state() -> Dict[str, Any]:
    return {
        "chat_id": None,
        "prefs": {
            "risk": None,               # "LOW"|"MEDIUM"|"HIGH"|None
            "focus": [],                # ["BTC","ETH"...]
            "avoid": [],                # ["ADA","XRP"...]
            "avoid_memecoins": False,   # True/False
        },
        "brain": {"sessions": {}}       # Integración con brain.py
    }

def load_state() -> Dict[str, Any]:
    try:
        if not os.path.exists(STATE_PATH):
            return _default_state()
            
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        # Merge profundo básico para asegurar que no falten llaves
        state = _default_state()
        if data:
            if "chat_id" in data: state["chat_id"] = data["chat_id"]
            if "prefs" in data: state["prefs"].update(data["prefs"])
            if "brain" in data: state["brain"] = data["brain"]
            
        return state
    except Exception as e:
        logger.error(f"Error cargando el estado: {e}")
        return _default_state()

def save_state(state: Dict[str, Any]) -> None:
    try:
        # Asegura que el directorio exista antes de intentar guardar
        os.makedirs(os.path.dirname(os.path.abspath(STATE_PATH)), exist_ok=True)
        
        # Guardado atómico: primero escribimos un temporal y luego renombramos
        # Esto evita que el archivo quede vacío si el bot se apaga justo al guardar.
        temp_path = STATE_PATH + ".tmp"
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        
        os.replace(temp_path, STATE_PATH)
    except Exception as e:
        logger.error(f"Error guardando el estado: {e}")

def set_chat_id(chat_id: int) -> None:
    st = load_state()
    st["chat_id"] = int(chat_id)
    save_state(st)
    logger.info(f"Chat ID guardado permanentemente: {chat_id}")

def update_prefs(patch: Dict[str, Any]) -> Dict[str, Any]:
    st = load_state()
    prefs = st.get("prefs", {})

    # Actualización de Riesgo
    if "risk" in patch:
        v = patch["risk"]
        if v in {"LOW", "MEDIUM", "HIGH", None}:
            prefs["risk"] = v

    # Memecoins
    if "avoid_memecoins" in patch:
        prefs["avoid_memecoins"] = bool(patch["avoid_memecoins"])

    # Monedas de interés (Focus)
    if "focus" in patch and isinstance(patch["focus"], list):
        cur = set(prefs.get("focus", []))
        for c in patch["focus"]:
            if isinstance(c, str) and 2 <= len(c) <= 6:
                cur.add(c.upper().strip())
        prefs["focus"] = sorted(list(cur))

    # Monedas a evitar (Avoid)
    if "avoid" in patch and isinstance(patch["avoid"], list):
        cur = set(prefs.get("avoid", []))
        for c in patch["avoid"]:
            if isinstance(c, str) and 2 <= len(c) <= 6:
                cur.add(c.upper().strip())
        prefs["avoid"] = sorted(list(cur))

    st["prefs"] = prefs
    save_state(st)
    return prefs

def clear_prefs() -> None:
    st = load_state()
    st["prefs"] = _default_state()["prefs"]
    save_state(st)
    logger.info("Preferencias globales reiniciadas.")
