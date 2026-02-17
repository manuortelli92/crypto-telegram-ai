import json
import os
from typing import Dict, Any, Optional

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
    }


def load_state() -> Dict[str, Any]:
    try:
        if not os.path.exists(STATE_PATH):
            return _default_state()
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        base = _default_state()
        base.update(data or {})
        base["prefs"].update((data or {}).get("prefs", {}) or {})
        base["prefs"]["focus"] = list(base["prefs"].get("focus", []) or [])
        base["prefs"]["avoid"] = list(base["prefs"].get("avoid", []) or [])
        base["prefs"]["avoid_memecoins"] = bool(base["prefs"].get("avoid_memecoins", False))
        return base
    except Exception:
        return _default_state()


def save_state(state: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def set_chat_id(chat_id: int) -> None:
    st = load_state()
    st["chat_id"] = int(chat_id)
    save_state(st)


def update_prefs(patch: Dict[str, Any]) -> Dict[str, Any]:
    """
    patch puede incluir: risk, focus, avoid, avoid_memecoins
    """
    st = load_state()
    prefs = st.get("prefs", {}) or {}

    if "risk" in patch:
        v = patch["risk"]
        prefs["risk"] = v if v in {"LOW", "MEDIUM", "HIGH", None} else prefs.get("risk")

    if "avoid_memecoins" in patch:
        prefs["avoid_memecoins"] = bool(patch["avoid_memecoins"])

    if "focus" in patch and patch["focus"] is not None:
        cur = set((prefs.get("focus") or []))
        for c in patch["focus"]:
            if isinstance(c, str) and 2 <= len(c) <= 6:
                cur.add(c.upper())
        prefs["focus"] = sorted(cur)

    if "avoid" in patch and patch["avoid"] is not None:
        cur = set((prefs.get("avoid") or []))
        for c in patch["avoid"]:
            if isinstance(c, str) and 2 <= len(c) <= 6:
                cur.add(c.upper())
        prefs["avoid"] = sorted(cur)

    st["prefs"] = prefs
    save_state(st)
    return prefs


def clear_prefs() -> None:
    st = load_state()
    st["prefs"] = _default_state()["prefs"]
    save_state(st)