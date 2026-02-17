import json
import os
from typing import Any, Dict

STATE_FILE = os.getenv("STATE_FILE", "state.json")

DEFAULT_STATE: Dict[str, Any] = {
    "chat_id": None,
    "prefs": {
        "lang": "es",
        "horizon": "weekly",
        "risk": "medium",   # low/medium/high
        "avoid": [],
        "focus": [],
        "max_picks": 3
    }
}

def load_state() -> Dict[str, Any]:
    if not os.path.exists(STATE_FILE):
        return json.loads(json.dumps(DEFAULT_STATE))
    with open(STATE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_state(state: Dict[str, Any]) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=True, indent=2)

def set_chat_id(chat_id: int) -> None:
    state = load_state()
    state["chat_id"] = chat_id
    save_state(state)

def update_prefs(patch: Dict[str, Any]) -> Dict[str, Any]:
    state = load_state()
    prefs = state.get("prefs", {})
    prefs.update(patch)
    state["prefs"] = prefs
    save_state(state)
    return state