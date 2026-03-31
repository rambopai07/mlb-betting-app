import streamlit as st
import requests
import pandas as pd
import uuid
from datetime import datetime
import math

st.set_page_config(layout="wide")

# -----------------------------
# HEADER DATE
# -----------------------------
today = datetime.now().strftime("%A %d %B %Y")
st.title("⚾ MLB Betting Engine v3 (Real Model Split)")
st.subheader(f"📅 Slate: {today}")

# -----------------------------
# BET TRACKER
# -----------------------------
if "bets" not in st.session_state:
    st.session_state.bets = []

# -----------------------------
# MLB SCHEDULE (CORRECT + STABLE)
# -----------------------------
def get_mlb_schedule():
    url = (
        "https://statsapi.mlb.com/api/v1/schedule"
        "?sportId=1"
        "&date=2026-03-31"
        "&hydrate=probablePitcher,teams"
    )

    data = requests.get(url).json()
    games = []

    for d in data.get("dates", []):
        for g in d.get("games", []):

            home = g["teams"]["home"]["team"]["name"]
            away = g["teams"]["away"]["team"]["name"]

            home_pitcher = g["teams"]["home"].get("probablePitcher", {}).get("fullName", "TBD")
            away_pitcher = g["teams"]["away"].get("probablePitcher", {}).get("fullName", "TBD")

            games.append((home, away, home_pitcher, away_pitcher))

    return games


games = get_mlb_schedule()

if not games:
    st.error("No games found for selected date.")
    st.stop()

# -----------------------------
# TEAM RATINGS (IMPROVED BASELINE)
# -----------------------------
team_strength = {
    "Dodgers": 8.9, "Yankees": 8.4, "Braves": 8.7, "Astros": 8.3,
    "Mets": 7.5, "Mariners": 7.8, "Guardians": 7.3, "Red Sox": 7.2,
    "Phillies": 8.1, "Blue Jays": 7.7, "Padres": 7.9, "Rangers": 7.8,
    "Orioles": 8.1, "Brewers": 7.4, "Cardinals": 7.3, "Giants": 7.4,
    "Rays": 7.7, "Tigers": 6.9, "Angels": 6.8, "Athletics": 6.5,
    "White Sox": 6.4, "Nationals": 6.6, "Pirates": 6.7,
    "Reds": 6.9, "Rockies": 6.2, "Marlins": 6.6, "Cubs": 7.5,
    "Diamondbacks": 7.5
}

# -----------------------------
# PITCHER IMPACT MODEL
# -----------------------------
def pitcher_rating(name):
    if name == "TBD":
        return 0

    elite = ["Cole", "Strider", "Burnes", "Skubal", "Valdez", "Gausman", "Wheeler"]
    good = ["Lugo", "Taillon", "Gray", "Pivetta", "Giolito", "Rodon"]

    for p in elite:
        if p in name:
            return 0.7
    for p in good:
        if p in name:
            return 0.3

    return 0.0

# -----------------------------
# MONEYLINE MODEL
# -----------------------------
def win_prob(home, away, hp, ap):

    h = team_strength.get(home, 7)
    a = team_strength.get(away, 7)

    h += pitcher_rating(hp)
    a += pitcher_rating(ap)

    h += 0.25  # home advantage

    diff = (h - a)

    prob = 1 / (1 + math.exp(-diff / 1.6))

    return max(0.20, min(0.80, prob))

# -----------------------------
# TOTALS MODEL
# -----------------------------
def totals_model(home, away, hp, ap):

    h_off = team_strength.get(home, 7)
    a_off = team_strength.get(away, 7)

    h_pitch = pitcher_rating(hp)
    a_pitch = pitcher_rating(ap)

    home_runs = (h_off + (5 - a_pitch)) / 2.1
    away_runs = (a_off + (5 - h_pitch)) / 2.1

    total = home_runs + away_runs

    return round(total, 2), round(home_runs, 2), round(away_runs, 2)

# -----------------------------
# SPREAD MODEL
# -----------------------------
def spread_model(home, away, hp, ap):

    prob = win_prob(home, away, hp, ap)

    return round((prob - 0.5) * 6, 2)

# -----------------------------
# EDGE FUNCTIONS (REAL VARIANCE NOW)
# -----------------------------
def ml_edge(model_prob):
    return round((model_prob - 0.5) * 100, 2)

def total_edge(total):
    return round((total - 8.6) * 4, 2)

def spread_edge(val):
    return round(val * 10, 2)

def grade(e):
    if e >= 3:
        return "🟢 BET"
    elif e >= 1:
        return "🟡 LEAN"
    return "🔴 NO BET"

# -----------------------------
# DISPLAY SLATE
# -----------------------------
st.header("📊 Full MLB Slate")

for home, away, hp, ap in games:

    st.markdown("---")

    st.subheader(f"{away} @ {home}")

    col1, col2, col3 = st.columns(3)

    # models
    p = win_prob(home, away, hp, ap)
    total, hr, ar = totals_model(home, away, hp, ap)
    spread = spread_model(home, away, hp, ap)

    with col1:
        st.write("🏟️ Pitchers")
        st.write(f"Away: {ap}")
        st.write(f"Home: {hp}")

        st.write("📈 Moneyline")
        st.write(f"Win Prob: {round(p*100,2)}%")
        e1 = ml_edge(p)
        st.write(f"Edge: {e1}% {grade(abs(e1))}")

    with col2:
        st.write("⚾ Totals")
        st.write(f"Projected Total: {total}")
        st.write(f"{home} TT: {hr}")
        st.write(f"{away} TT: {ar}")

        e2 = total_edge(total)
        st.write(f"Edge: {e2}% {grade(abs(e2))}")

    with col3:
        st.write("📊 Spread")
        st.write(f"Run Diff: {spread}")

        e3 = spread_edge(spread)
        st.write(f"Edge: {e3}% {grade(abs(e3))}")

    # BET TRACKER
    if st.button(f"➕ Add Bet {away} @ {home}", key=str(uuid.uuid4())):
        st.session_state.bets.append({
            "game": f"{away} @ {home}",
            "ml_prob": round(p, 3),
            "total": total,
            "spread": spread,
            "status": "open"
        })

# -----------------------------
# TRACKER
# -----------------------------
st.header("📒 Bet Tracker")

if st.session_state.bets:
    st.dataframe(pd.DataFrame(st.session_state.bets))
else:
    st.info("No bets added yet.")
