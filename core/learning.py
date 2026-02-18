import json
import os
import logging

logger = logging.getLogger(__name__)

# Es recomendable usar una ruta absoluta o configurable para entornos como Railway
LEARN_FILE = os.getenv("LEARN_FILE_PATH", "learning_state.json")

def load_learning():
    if not os.path.exists(LEARN_FILE):
        return {}
    try:
        with open(LEARN_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error cargando aprendizaje: {e}")
        return {}

def save_learning(state):
    try:
        with open(LEARN_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=4)
    except Exception as e:
        logger.error(f"No se pudo guardar el aprendizaje: {e}")

def register_user_interest(text: str):
    if not text:
        return

    # Limpiamos un poco el texto para evitar símbolos extraños
    clean_text = text.upper().replace("?", "").replace("!", "").replace(",", " ")
    words = clean_text.split()

    state = load_learning()
    changed = False

    # Lista negra de palabras cortas que NO son criptos para no ensuciar el aprendizaje
    blacklist = {"HOLA", "CHAU", "INFO", "DAME", "ESTA", "BIEN", "TODO", "TOP", "COMO", "CHÉ"}

    for w in words:
        # Detecta símbolos tipo BTC, ETH, SOL
        # Agregamos validación para que no esté en la blacklist y tenga longitud razonable
        if 2 <= len(w) <= 6 and w.isalpha() and w not in blacklist:
            state[w] = state.get(w, 0) + 1
            changed = True

    if changed:
        save_learning(state)

def get_learning_boost(symbol: str) -> float:
    """
    Devuelve un pequeño plus para el motor de puntuación basado en el interés.
    """
    if not symbol:
        return 0.0
        
    state = load_learning()
    score = state.get(symbol.upper(), 0)

    # El boost crece con el interés, pero tiene un techo (8 puntos) 
    # para que una moneda popular no oculte a las que realmente rinden.
    return min(score * 0.5, 8.0)
