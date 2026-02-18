import json
import os
import logging
import threading
import math
from typing import Dict, Any

logger = logging.getLogger(__name__)

# Archivo exclusivo para las estadísticas de popularidad de monedas
LEARN_FILE = os.getenv("LEARN_FILE_PATH", "learning_state.json")
_CACHED_STATE = None
_STATE_LOCK = threading.Lock()

def load_learning() -> Dict[str, Any]:
    """Carga el ranking de interés global."""
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
            logger.error(f"❌ Error cargando learning.json: {e}")
            return {}

def save_learning(state: Dict[str, Any]):
    """Guarda las estadísticas de interés de forma atómica."""
    try:
        with _STATE_LOCK:
            temp_file = LEARN_FILE + ".tmp"
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=4)
            os.replace(temp_file, LEARN_FILE)
    except Exception as e:
        logger.error(f"❌ Error persistiendo learning: {e}")

def register_user_interest(text: str):
    """Analiza el texto y sube el puntaje de las monedas mencionadas (BTC, ETH, etc)."""
    if not text or len(text) > 500: return
    
    clean_text = text.upper().replace("?", "").replace("!", "").replace(",", " ").replace("$", "")
    words = clean_text.split()
    
    state = load_learning()
    changed = False
    blacklist = {
        "HOLA", "CHAU", "INFO", "DAME", "ESTA", "BIEN", "TODO", "TOP", 
        "COMO", "CHE", "GRACIAS", "PRECIO", "CUANTO", "COMPRAR", "VENDER"
    }
    
    for w in words:
        # Si la palabra parece un ticker (2-5 letras) y no está en la blacklist
        if 2 <= len(w) <= 5 and w.isalpha() and w not in blacklist:
            state[w] = state.get(w, 0) + 1
            changed = True
            
    if changed:
        save_learning(state)

def get_learning_boost(symbol: str) -> float:
    """Retorna un bono de puntaje si la moneda es muy popular en el chat."""
    if not symbol: return 0.0
    state = load_learning()
    interest_count = state.get(symbol.upper(), 0)
    if interest_count <= 0: return 0.0
    
    # El primer interés vale mucho, el número 1000 no rompe el ranking
    boost = math.log10(interest_count + 1) * 3 
    return min(boost, 10.0) # Máximo 10 puntos de boost
