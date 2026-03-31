import streamlit as st
import pandas as pd
import uuid
import random

st.set_page_config(layout="wide")
st.title("⚾ MLB Betting Engine v3")

# -----------------------------
# SESSION DB
# -----------------------------
if "bets" not in st.session_state:
    st.session_state.bets = []

# -----------------------------
# SIMULATED FULL MLB SLATE
# (next upgrade = real API)
# -----------------------------
teams = [
    "Dodgers","Guardians","Yankees","Mariners","Braves","Mets",
    "Astros","Red Sox","Cubs","Cardinals","Phillies","Nationals",
    "Blue Jays","Rays","Padres","Giants"
]

random.shuffle(teams)
games = [(teams[i], teams[i+1]) for i in range(0, len(teams), 2)]

# -----------------------------
# MODEL FUNCTIONS
# -----------------------------
def win_prob():
    return round(random.uniform(0.45, 0.65), 3)

def runs_projection():
    return round(random.uniform(3.5, 5.5), 1)

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

    with col1:
        st.subheader(f"{home} vs {away}")

        # Moneyline
        model_ml = win_prob()
        book_ml = model_ml - random.uniform(-0.02, 0.02)
        e_ml = edge(model_ml, book_ml)

        st.write(f"**ML ({home})**: {round(model_ml*100,1)}%")
        st.write(f"Edge: {e_ml}% {grade(e_ml)}")

        # Spread
        spread_prob = model_ml - 0.05
        e_spread = edge(spread_prob, book_ml)

        st.write(f"**Spread -1.5 ({home})**")
        st.write(f"Edge: {e_spread}% {grade(e_spread)}")

    with col2:
        # Totals
        home_runs = runs_projection()
        away_runs = runs_projection()
        total = home_runs + away_runs

        st.write(f"**Total Runs**: {total}")
        st.write(f"**{home} TT**: {home_runs}")
        st.write(f"**{away} TT**: {away_runs}")

        total_edge = edge(total/10, 0.5)

        st.write(f"Edge (Total): {total_edge}% {grade(total_edge)}")

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

# -----------------------------
# SETTLE
# -----------------------------
st.header("✔️ Settle Bet")

bet_id = st.text_input("Bet ID")
result = st.selectbox("Result", ["win", "loss"])

if st.button("Settle"):
    for b in st.session_state.bets:
        if b["id"] == bet_id:
            b["status"] = result
            st.success("Settled")

# -----------------------------
# DELETE
# -----------------------------
st.header("❌ Delete Bet")

del_id = st.text_input("Delete ID")

if st.button("Delete"):
    st.session_state.bets = [b for b in st.session_state.bets if b["id"] != del_id]
    st.warning("Deleted")
