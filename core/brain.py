import time
import logging
from typing import Dict, List, Optional, Any

# Configuración del logger para diagnóstico
logger = logging.getLogger(__name__)

def _now() -> float:
    return time.time()

def _trim(s: str, max_len: int = 800) -> str:
    """Evita saturar la memoria con mensajes gigantes."""
    s = (s or "").strip()
    if len(s) <= max_len:
        return s
    return s[:max_len].rstrip() + "..."

def ensure_brain(state: Any) -> Dict:
    """
    DIAGNÓSTICO: Verifica y repara la estructura del 'cerebro' del bot.
    Si el estado llega como None o formato incorrecto, lo inicializa.
    """
    if not isinstance(state, dict):
        logger.warning("⚠️ El 'state' no es un diccionario. Reiniciando base de datos temporal.")
        state = {}
        
    if "brain" not in state or not isinstance(state["brain"], dict):
        state["brain"] = {"sessions": {}, "global_prefs": {}}
    
    brain = state["brain"]
    if "sessions" not in brain: brain["sessions"] = {}
    if "global_prefs" not in brain: brain["global_prefs"] = {}
    return brain

def get_session(state: Dict, chat_id: int) -> Dict:
    """Recupera la sesión del usuario o crea una nueva con valores por defecto."""
    brain = ensure_brain(state)
    sid = str(chat_id)
    
    if sid not in brain["sessions"] or not isinstance(brain["sessions"][sid], dict):
        logger.info(f"🆕 Creando nueva sesión para el usuario: {sid}")
        brain["sessions"][sid] = {
            "history": [],        
            "facts": {},          
            "last_mode": "SEMANAL",
            "last_top_n": 20,
            "created_at": _now()
        }
    
    sess = brain["sessions"][sid]
    # Reparación interna por si faltan llaves
    if "history" not in sess: sess["history"] = []
    if "facts" not in sess: sess["facts"] = {}
    return sess

def add_turn(state: Dict, chat_id: int, role: str, text: str, max_turns: int = 10) -> None:
    """Guarda un turno de conversación y aplica poda automática."""
    try:
        sess = get_session(state, chat_id)
        sess["history"].append({
            "ts": _now(), 
            "role": role, 
            "text": _trim(text, 1000)
        })

        # Mantiene la memoria corta para no confundir a la IA
        if len(sess["history"]) > max_turns * 2:
            sess["history"] = sess["history"][-max_turns * 2:]
            logger.debug(f"✂️ Podando historial del usuario {chat_id}")
    except Exception as e:
        logger.error(f"❌ Error al añadir turno: {e}")

def recent_context_text(state: Dict, chat_id: int, max_turns: int = 6) -> str:
    """Genera un bloque de texto con el contexto para que Gemini lo lea."""
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
    """Detecta si el usuario quiere ver datos Diarios, Semanales o Mensuales."""
    t = (text or "").lower()
    if any(k in t for k in ["mensual", "mes"]): return "MENSUAL"
    if any(k in t for k in ["diario", "hoy", "24h"]): return "DIARIO"
    if any(k in t for k in ["semanal", "semana", "7d"]): return "SEMANAL"
    return None

def parse_top_n(text: str) -> Optional[int]:
    """Extrae el número de monedas que el usuario quiere analizar (Top 10, Top 50, etc)."""
    t = (text or "").lower().replace(",", " ")
    if "top" in t:
        parts = t.split()
        for i, word in enumerate(parts):
            if word == "top" and i + 1 < len(parts) and parts[i+1].isdigit():
                val = int(parts[i+1])
                return max(5, min(100, val))
    
    for tok in t.split():
        if tok.isdigit():
            val = int(tok)
            if 5 <= val <= 250: # Rango razonable
                return val
    return None

def extract_prefs_patch(text: str) -> Dict:
    """
    INTELIGENCIA: Extrae preferencias implícitas del usuario.
    Ejemplo: 'No me muestres USDT' -> añade USDT a lista de evitar.
    """
    t = (text or "").lower()
    patch: Dict = {}

    # Detección de perfil de riesgo
    if any(k in t for k in ["riesgo bajo", "conservador", "low"]): 
        patch["risk_pref"] = "LOW"
    elif any(k in t for k in ["riesgo medio", "medium"]): 
        patch["risk_pref"] = "MEDIUM"
    elif any(k in t for k in ["riesgo alto", "agresivo", "high"]): 
        patch["risk_pref"] = "HIGH"

    def _clean_coins(raw_text: str) -> List[str]:
        potential = raw_text.replace(",", " ").replace(".", " ").upper().split()
        # Filtra solo lo que parece un Ticker (BTC, ETH...)
        return [c for c in potential if 2 <= len(c) <= 6 and c.isalpha()]

    # Lógica de exclusión
    if any(k in t for k in ["evita", "sacame", "quitar", "sin "]):
        for key in ["evita ", "sacame ", "quitar ", "sin "]:
            if key in t:
                coins_text = t.split(key, 1)[1]
                patch["avoid"] = _clean_coins(coins_text)
                break

    # Lógica de enfoque
    if any(k in t for k in ["prefiero", "me gusta", "foco en"]):
        for key in ["prefiero ", "me gusta ", "foco en "]:
            if key in t:
                coins_text = t.split(key, 1)[1]
                patch["focus"] = _clean_coins(coins_text)
                break

    return patch

def apply_patch_to_session(state: Dict, chat_id: int, user_text: str) -> Dict:
    """
    ACTUALIZADOR MAESTRO: Es la función que llamará el Engine.
    Sincroniza lo que el usuario dijo con lo que el bot recordará.
    """
    try:
        sess = get_session(state, chat_id)

        # 1. Detectar cambios de modo o cantidad
        m = detect_mode(user_text)
        if m: 
            sess["last_mode"] = m
            logger.info(f"📊 Modo cambiado a {m} para {chat_id}")

        tn = parse_top_n(user_text)
        if tn: 
            sess["last_top_n"] = tn
            logger.info(f"🔢 Top N cambiado a {tn} para {chat_id}")

        # 2. Aprender nuevas preferencias
        patch = extract_prefs_patch(user_text)
        if patch:
            facts = sess["facts"]
            
            if "avoid" in patch:
                current = set(facts.get("avoid", []))
                current.update(patch["avoid"])
                facts["avoid"] = sorted(list(current))
                logger.info(f"🚫 Lista negra actualizada: {facts['avoid']}")
                
            if "focus" in patch:
                current = set(facts.get("focus", []))
                current.update(patch["focus"])
                facts["focus"] = sorted(list(current))
                logger.info(f"⭐ Lista de interés actualizada: {facts['focus']}")
                
            if "risk_pref" in patch:
                facts["risk_pref"] = patch["risk_pref"]
                logger.info(f"⚖️ Perfil de riesgo: {patch['risk_pref']}")

        # 3. Respuesta estructurada para el Engine
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
        # Devolver default para que el bot no muera
        return {"mode": "SEMANAL", "top_n": 20, "risk_pref": None, "avoid": [], "focus": [], "context": ""}
