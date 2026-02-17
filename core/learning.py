import json
import os

LEARN_FILE = "learning_state.json"


def load_learning():

    if not os.path.exists(LEARN_FILE):
        return {}

    try:
        with open(LEARN_FILE, "r") as f:
            return json.load(f)
    except:
        return {}


def save_learning(state):

    with open(LEARN_FILE, "w") as f:
        json.dump(state, f)


def register_user_interest(text: str):

    if not text:
        return

    words = text.upper().split()

    state = load_learning()

    for w in words:

        # detecta simbolos tipo BTC ETH SOL ADA
        if len(w) <= 6 and w.isalpha():

            if w not in state:
                state[w] = 0

            state[w] += 1

    save_learning(state)


def get_learning_boost(symbol):

    state = load_learning()

    score = state.get(symbol, 0)

    # limite para no romper el ranking
    return min(score * 0.5, 8)