import streamlit as st
import pandas as pd
import uuid

st.set_page_config(layout="wide")
st.title("⚾ MLB Betting Engine v4 (Real Model Base)")

# -----------------------------
# SESSION DB
# -----------------------------
if "bets" not in st.session_state:
    st.session_state.bets = []

# -----------------------------
# REALISTIC TEAM DATA (BASE MODEL)
# -----------------------------
teams = {
    "Dodgers": {"pitch": 8.5, "off": 5.3, "bull": 7.8},
    "Guardians": {"pitch": 7.2, "off": 4.4, "bull": 7.0},
    "Yankees": {"pitch": 8.1, "off": 5.0, "bull": 7.5},
    "Mariners": {"pitch": 7.8, "off": 4.5, "bull": 7.3},
    "Braves": {"pitch": 8.3, "off": 5.2, "bull": 7.6},
    "Mets": {"pitch": 7.4, "off": 4.6, "bull": 6.9},
    "Astros": {"pitch": 8.0, "off": 5.1, "bull": 7.4},
    "Red Sox": {"pitch": 7.0, "off": 4.7, "bull": 6.8}
}

games = [
    ("Dodgers", "Guardians"),
    ("Yankees", "Mariners"),
    ("Braves", "Mets"),
    ("Astros", "Red Sox")
]

# -----------------------------
# MODEL FUNCTIONS
# -----------------------------
def win_prob(home, away):
    h = teams[home]
    a = teams[away]

    score = (
        (h["pitch"] - a["pitch"]) * 0.5 +
        (h["off"] - a["off"]) * 0.3 +
        (h["bull"] - a["bull"]) * 0.2
    )

    prob = 0.5 + score / 10
    return max(0.3, min(0.7, prob))

def runs_proj(team):
    t = teams[team]
    return round((t["off"] * 0.7 + t["pitch"] * 0.3) / 2, 1)

def edge(model, book):
    return round((model - book) * 100, 2)

def grade(e):
    if e >= 3:
        return "🟢 BET"
    elif e >= 1:
        return "🟡 LEAN"
    return "🔴 NO BET"

# -----------------------------
# GAME BOARD
# -----------------------------
st.header("📊 Full Game Board")

for home, away in games:

    col1, col2 = st.columns(2)

    model_ml = win_prob(home, away)
    book_ml = model_ml - 0.02  # placeholder

    e_ml = edge(model_ml, book_ml)

    with col1:
        st.subheader(f"{home} vs {away}")

        st.write(f"ML ({home}): {round(model_ml*100,1)}%")
        st.write(f"Edge: {e_ml}% {grade(e_ml)}")

        spread_prob = model_ml - 0.08
        e_spread = edge(spread_prob, book_ml)

        st.write(f"Spread -1.5 ({home}) Edge: {e_spread}% {grade(e_spread)}")

    with col2:
        home_runs = runs_proj(home)
        away_runs = runs_proj(away)
        total = home_runs + away_runs

        st.write(f"Total: {total}")
        st.write(f"{home} TT: {home_runs}")
        st.write(f"{away} TT: {away_runs}")

        total_edge = edge(total/10, 0.5)

        st.write(f"Total Edge: {total_edge}% {grade(total_edge)}")

    if st.button(f"➕ Add Bet {home}"):
        st.session_state.bets.append({
            "id": str(uuid.uuid4())[:8],
            "game": f"{home} vs {away}",
            "edge": e_ml,
            "status": "pending"
        })
        st.success("Bet added")

# -----------------------------
# TRACKER
# -----------------------------
st.header("📒 Bet Tracker")

if st.session_state.bets:
    st.dataframe(pd.DataFrame(st.session_state.bets))
else:
    st.info("No bets yet")
