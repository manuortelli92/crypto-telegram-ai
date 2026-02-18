import json, os, threading, math
from typing import Dict, Any

LEARN_FILE = "learning_state.json"
_CACHED_STATE = None
_STATE_LOCK = threading.Lock()

def load_learning():
    global _CACHED_STATE
    with _STATE_LOCK:
        if _CACHED_STATE is not None: return _CACHED_STATE
        if not os.path.exists(LEARN_FILE): return {}
        try:
            with open(LEARN_FILE, "r", encoding="utf-8") as f:
                _CACHED_STATE = json.load(f)
                return _CACHED_STATE
        except: return {}

def save_learning(state):
    with _STATE_LOCK:
        with open(LEARN_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=4)

def register_user_interest(text: str):
    if not text: return
    words = text.upper().replace("$", "").split()
    state = load_learning()
    changed = False
    for w in words:
        if 2 <= len(w) <= 5 and w.isalpha():
            state[w] = state.get(w, 0) + 1
            changed = True
    if changed: save_learning(state)

def get_learning_boost(symbol: str) -> float:
    state = load_learning()
    count = state.get(symbol.upper(), 0)
    return min(math.log10(count + 1) * 3, 10.0) if count > 0 else 0.0
