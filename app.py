import streamlit as st
import pandas as pd
import requests
import uuid
import datetime

st.set_page_config(layout="wide")
st.title("⚾ MLB Betting Engine v5 (Live Slate + Pitchers)")

# -----------------------------
# SESSION STORAGE
# -----------------------------
if "bets" not in st.session_state:
    st.session_state.bets = []

# -----------------------------
# GET REAL MLB SLATE + PITCHERS
# ESPN PROBABLE PITCHERS FEED
# -----------------------------
def get_mlb_games():
    url = "https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/scoreboard"
    data = requests.get(url).json()

    games = []

    for event in data.get("events", []):
        try:
            comp = event["competitions"][0]
            home = comp["competitors"][0]["team"]["displayName"]
            away = comp["competitors"][1]["team"]["displayName"]

            home_pitcher = "TBD"
            away_pitcher = "TBD"

            # try pitcher info
            for c in comp["competitors"]:
                try:
                    if "probables" in c:
                        p = c["probables"][0]["athlete"]["displayName"]
                    else:
                        p = "TBD"
                except:
                    p = "TBD"

                if c["homeAway"] == "home":
                    home_pitcher = p
                else:
                    away_pitcher = p

            games.append((home, away, home_pitcher, away_pitcher))

        except:
            continue

    return games

games = get_mlb_games()

# fallback if API fails
if not games:
    games = [
        ("Dodgers", "Guardians", "TBD", "TBD"),
        ("Yankees", "Mariners", "TBD", "TBD")
    ]

# -----------------------------
# SIMPLE TEAM MODEL (UPGRADE LATER TO REAL STATS FEED)
# -----------------------------
team_strength = {
    "Dodgers": 8.6,
    "Yankees": 8.2,
    "Braves": 8.4,
    "Astros": 8.1,
    "Mets": 7.3,
    "Mariners": 7.6,
    "Guardians": 7.2,
    "Red Sox": 7.0
}

# -----------------------------
# MODEL FUNCTIONS
# -----------------------------
def win_prob(home, away):
    h = team_strength.get(home, 7.5)
    a = team_strength.get(away, 7.5)

    diff = (h - a) / 10
    prob = 0.5 + diff

    return max(0.30, min(0.70, prob))

def edge(model, book):
    return round((model - book) * 100, 2)

def grade(e):
    if e >= 3:
        return "🟢 BET"
    elif e >= 1:
        return "🟡 LEAN"
    return "🔴 NO BET"

def run_projection(home, away):
    h = team_strength.get(home, 7.5)
    a = team_strength.get(away, 7.5)
    return round((h + a) / 3, 1)

# -----------------------------
# GAME BOARD
# -----------------------------
st.header("📊 Live MLB Slate")

for home, away, hp, ap in games:

    col1, col2 = st.columns(2)

    model_ml = win_prob(home, away)
    book_ml = model_ml - 0.015

    e_ml = edge(model_ml, book_ml)

    with col1:
        st.subheader(f"{home} vs {away}")

        # pitchers
        st.write("🏟️ Pitching Matchup")
        st.write(f"{home}: {hp}")
        st.write(f"{away}: {ap}")

        # ML
        st.write(f"Moneyline ({home}): {round(model_ml*100,1)}%")
        st.write(f"Edge: {e_ml}% {grade(e_ml)}")

        # Spread
        spread_model = model_ml - 0.08
        e_spread = edge(spread_model, book_ml)
        st.write(f"Spread Edge: {e_spread}% {grade(e_spread)}")

    with col2:
        home_runs = run_projection(home, away)
        away_runs = run_projection(away, home)
        total = home_runs + away_runs

        st.write(f"Total Runs: {total}")
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

del_id = st.text_input("Delete Bet ID")

if st.button("Delete"):
    st.session_state.bets = [b for b in st.session_state.bets if b["id"] != del_id]
    st.warning("Deleted")
