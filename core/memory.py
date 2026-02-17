import json
import os

STATE_FILE = "bot_state.json"

def load_state():

    if not os.path.exists(STATE_FILE):
        return {"prefs": {}, "chat_id": None}

    try:
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    except:
        return {"prefs": {}, "chat_id": None}

def save_state(state):

    with open(STATE_FILE, "w") as f:
        json.dump(state, f)

def set_chat_id(chat_id):

    state = load_state()
    state["chat_id"] = chat_id
    save_state(state)

def update_prefs(patch):

    state = load_state()
    prefs = state.get("prefs", {})

    prefs.update(patch)

    state["prefs"] = prefs
    save_state(state)