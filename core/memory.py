import json
import os
import logging
import threading
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# En Railway, si no hay volumen montado, esto es temporal por cada deploy.
# Centralizamos la ruta para que siempre apunte al lugar correcto.
STATE_PATH = os.getenv("STATE_PATH", "core/state.json")

# Lock de seguridad para evitar que dos procesos escriban al mismo tiempo
_STATE_LOCK = threading.Lock()

def _default_state() -> Dict[str, Any]:
    """Define la estructura base del bot para evitar errores de llave inexistente."""
    return {
        "chat_id": None,
        "is_active": True,
        "prefs": {
            "risk": "MEDIUM",           # Valor por defecto seguro
            "focus": [],                
            "avoid": [],                
            "avoid_memecoins": False,   
        },
        "brain": {"sessions": {}}       # Conector con learning.py
    }

def load_state() -> Dict[str, Any]:
    """Carga el estado con validación de estructura (Safe Load)."""
    with _STATE_LOCK:
        try:
            if not os.path.exists(STATE_PATH):
                logger.info("📄 No se encontró archivo de estado. Creando uno nuevo.")
                return _default_state()
                
            with open(STATE_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            # Merge inteligente: asegura que si agregamos funciones nuevas al bot, 
            # el JSON viejo no rompa el sistema.
            state = _default_state()
            if isinstance(data, dict):
                if "chat_id" in data: state["chat_id"] = data["chat_id"]
                if "prefs" in data: state["prefs"].update(data["prefs"])
                if "brain" in data: state["brain"] = data["brain"]
                if "is_active" in data: state["is_active"] = data["is_active"]
                
            return state
        except Exception as e:
            logger.error(f"❌ Error crítico cargando el estado: {e}")
            return _default_state()

def save_state(state: Dict[str, Any]) -> None:
    """Guarda el estado usando escritura atómica y validación de directorio."""
    with _STATE_LOCK:
        try:
            # Asegurar que la carpeta core/ existe
            dir_name = os.path.dirname(os.path.abspath(STATE_PATH))
            if not os.path.exists(dir_name):
                os.makedirs(dir_name, exist_ok=True)
            
            # Guardado atómico (Temporal -> Reemplazo)
            temp_path = STATE_PATH + ".tmp"
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=4)
            
            os.replace(temp_path, STATE_PATH)
            logger.debug("✅ Estado guardado exitosamente.")
        except Exception as e:
            logger.error(f"❌ Error guardando el estado: {e}")

def get_admin_id() -> Optional[int]:
    """Recupera el chat_id del dueño para funciones administrativas."""
    st = load_state()
    return st.get("chat_id")

def set_chat_id(chat_id: int) -> None:
    """Define quién es el administrador principal del bot."""
    st = load_state()
    st["chat_id"] = int(chat_id)
    save_state(st)
    logger.info(f"👑 Admin ID configurado: {chat_id}")

def update_prefs(patch: Dict[str, Any]) -> Dict[str, Any]:
    """Actualiza preferencias globales de filtrado."""
    st = load_state()
    prefs = st.get("prefs", _default_state()["prefs"])

    # Riesgo
    if "risk" in patch and patch["risk"] in {"LOW", "MEDIUM", "HIGH"}:
        prefs["risk"] = patch["risk"]

    # Memecoins
    if "avoid_memecoins" in patch:
        prefs["avoid_memecoins"] = bool(patch["avoid_memecoins"])

    # Listas de Tickers (Focus/Avoid)
    for key in ["focus", "avoid"]:
        if key in patch and isinstance(patch[key], list):
            current = set(prefs.get(key, []))
            for item in patch[key]:
                if isinstance(item, str) and 2 <= len(item) <= 6:
                    current.add(item.upper().strip())
            prefs[key] = sorted(list(current))

    st["prefs"] = prefs
    save_state(st)
    return prefs

def clear_all_state() -> None:
    """Borra todo y reinicia el bot a fábrica."""
    save_state(_default_state())
    logger.warning("🚨 ESTADO REINICIADO POR COMPLETO.")
