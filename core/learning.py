import json
import os
import logging
import threading
from typing import Dict, Any

logger = logging.getLogger(__name__)

# En Railway, lo ideal es usar /tmp o un Volume Montado. 
# Si no tenés volumen, esto se borrará al reiniciar, pero no romperá el bot.
LEARN_FILE = os.getenv("LEARN_FILE_PATH", "learning_state.json")

# Memoria volátil para no leer el disco en cada mensaje (Performance Boost)
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
                logger.info(f"🧠 Memoria cargada: {len(_CACHED_STATE)} conceptos aprendidos.")
                return _CACHED_STATE
        except Exception as e:
            logger.error(f"❌ Error cargando JSON de aprendizaje: {e}")
            _CACHED_STATE = {}
            return _CACHED_STATE

def save_learning(state: Dict[str, Any]):
    """Guarda el estado asegurando que no se corrompa el archivo."""
    try:
        with _STATE_LOCK:
            # Escribimos en un archivo temporal primero y luego renombramos (atómico)
            temp_file = LEARN_FILE + ".tmp"
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=4)
            os.replace(temp_file, LEARN_FILE)
    except Exception as e:
        logger.error(f"❌ Error persistiendo aprendizaje: {e}")

def register_user_interest(text: str):
    """
    Analiza el texto del usuario y detecta interés en Tickers específicos.
    Mejorado con validación de Tickers reales.
    """
    if not text or len(text) > 500: # Protección contra ataques de texto largo
        return

    clean_text = text.upper().replace("?", "").replace("!", "").replace(",", " ").replace("$", "")
    words = clean_text.split()

    state = load_learning()
    changed = False

    # Blacklist expandida para la City Argentina
    blacklist = {
        "HOLA", "CHAU", "INFO", "DAME", "ESTA", "BIEN", "TODO", "TOP", 
        "COMO", "CHE", "GRACIAS", "PRECIO", "CUANTO", "COMPRAR", "VENDER",
        "MERCADO", "BOT", "AYUDA", "QUE", "POR", "PARA"
    }

    for w in words:
        # Un Ticker suele tener entre 2 y 5 letras y ser solo letras
        if 2 <= len(w) <= 5 and w.isalpha() and w not in blacklist:
            state[w] = state.get(w, 0) + 1
            changed = True
            logger.debug(f"📈 Interés incrementado para: {w}")

    if changed:
        save_learning(state)

def get_learning_boost(symbol: str) -> float:
    """
    Calcula el 'Heat Score' de una moneda. 
    Si la gente pregunta mucho por ella, sube en el ranking del Engine.
    """
    if not symbol:
        return 0.0
        
    state = load_learning()
    # Usamos .get con 0 por si la moneda es nueva
    interest_count = state.get(symbol.upper(), 0)

    # Logaritmo suavizado: El primer interés vale mucho, 
    # pero el interés número 1000 no debe romper el ranking.
    # Techo máximo: 10 puntos de boost.
    if interest_count <= 0: return 0.0
    
    import math
    boost = math.log10(interest_count + 1) * 3 
    return min(boost, 10.0)
