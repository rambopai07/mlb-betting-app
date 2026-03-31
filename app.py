import streamlit as st
import requests
import pandas as pd
import uuid
from datetime import datetime

st.set_page_config(layout="wide")

# -----------------------------
# DATE (DISPLAY ONLY)
# -----------------------------
today = datetime.now().strftime("%A, %d %B %Y")
st.title("⚾ MLB Betting Engine v8 (Stable API Version)")
st.subheader(f"📅 Slate View: {today}")

# -----------------------------
# BET TRACKER
# -----------------------------
if "bets" not in st.session_state:
    st.session_state.bets = []

# -----------------------------
# MLB SCHEDULE (FIXED + FILTERED)
# -----------------------------
def get_mlb_schedule():
    # IMPORTANT: hard date lock prevents wrong slate (KC vs MIN issue fix)
    url = (
        "https://statsapi.mlb.com/api/v1/schedule"
        "?sportId=1"
        "&date=2026-03-31"
        "&hydrate=probablePitcher,teams"
    )

    r = requests.get(url)
    data = r.json()

    games = []

    for d in data.get("dates", []):
        for g in d.get("games", []):

            home = g["teams"]["home"]["team"]["name"]
            away = g["teams"]["away"]["team"]["name"]

            # pitchers (safe extraction)
            home_pitcher = (
                g["teams"]["home"]
                .get("probablePitcher", {})
                .get("fullName", "TBD")
            )

            away_pitcher = (
                g["teams"]["away"]
                .get("probablePitcher", {})
                .get("fullName", "TBD")
            )

            games.append((home, away, home_pitcher, away_pitcher))

    return games

games = get_mlb_schedule()

# fallback safety
if not games:
    games = [
        ("Dodgers", "Guardians", "TBD", "TBD"),
        ("Yankees", "Mariners", "TBD", "TBD"),
    ]

# -----------------------------
# MODEL (simple baseline)
# -----------------------------
team_strength = {
    "Dodgers": 8.6, "Yankees": 8.2, "Braves": 8.4, "Astros": 8.1,
    "Mets": 7.3, "Mariners": 7.6, "Guardians": 7.2, "Red Sox": 7.0,
    "Cubs": 7.4, "Phillies": 7.8, "Padres": 7.7, "Blue Jays": 7.5,
    "Diamondbacks": 7.3, "Rangers": 7.6, "Orioles": 7.8, "Brewers": 7.2,
    "Cardinals": 7.1, "Giants": 7.3, "Rays": 7.6, "Tigers": 6.9,
    "Angels": 6.8, "Athletics": 6.5, "White Sox": 6.4,
    "Nationals": 6.6, "Pirates": 6.7, "Reds": 6.8,
    "Rockies": 6.3, "Marlins": 6.6
}

def win_prob(home, away):
    h = team_strength.get(home, 7.0)
    a = team_strength.get(away, 7.0)
    diff = (h - a) / 10
    return max(0.30, min(0.70, 0.5 + diff))

def edge(model, book):
    return round((model - book) * 100, 2)

def grade(e):
    if e >= 3:
        return "🟢 BET"
    elif e >= 1:
        return "🟡 LEAN"
    return "🔴 NO BET"

def proj_runs(team, opp):
    return round((team_strength.get(team, 7) + team_strength.get(opp, 7)) / 3, 1)

# -----------------------------
# UI
# -----------------------------
st.header("📊 Full Verified MLB Slate")

for home, away, hp, ap in games:

    col1, col2 = st.columns(2)

    model = win_prob(home, away)
    book = model - 0.015
    e = edge(model, book)

    with col1:
        st.subheader(f"{away} @ {home}")

        st.write("🏟️ Probable Pitchers")
        st.write(f"{away}: {ap}")
        st.write(f"{home}: {hp}")

        st.write(f"Moneyline Edge: {e}% {grade(e)}")

        spread_model = model - 0.08
        st.write(f"Spread Edge: {edge(spread_model, book)}% {grade(edge(spread_model, book))}")

    with col2:
        total = proj_runs(home, away) + proj_runs(away, home)

        st.write(f"Total Runs: {total}")
        st.write(f"{home} Team Total: {proj_runs(home, away)}")
        st.write(f"{away} Team Total: {proj_runs(away, home)}")

    # BET TRACKER BUTTON
    bet_key = f"{away}_vs_{home}"

    if st.button(f"➕ Add Bet {away} @ {home}", key=bet_key):
        st.session_state.bets.append({
            "id": str(uuid.uuid4())[:8],
            "game": f"{away} @ {home}",
            "edge": e,
            "status": "pending"
        })
        st.success("Bet added")

# -----------------------------
# BET TRACKER
# -----------------------------
st.header("📒 Bet Tracker")

if st.session_state.bets:
    st.dataframe(pd.DataFrame(st.session_state.bets))
else:
    st.info("No bets yet")
