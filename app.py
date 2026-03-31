import streamlit as st
import requests
import pandas as pd
import uuid
import math
from datetime import datetime

st.set_page_config(layout="wide")

# -----------------------------
# HEADER
# -----------------------------
today = datetime.now().strftime("%A %d %B %Y")
st.title("⚾ MLB Betting Engine v4 (LIVE TEAM STRENGTH)")
st.subheader(f"📅 Slate: {today}")

# -----------------------------
# BET TRACKER
# -----------------------------
if "bets" not in st.session_state:
    st.session_state.bets = []

# -----------------------------
# MLB SCHEDULE (CORRECT)
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

# -----------------------------
# LIVE TEAM STATS (MLB API)
# -----------------------------
def get_team_offense_rankings():
    """
    Pulls live MLB hitting stats and converts into strength score.
    """

    url = "https://statsapi.mlb.com/api/v1/stats?stats=season&group=hitting&sportId=1"
    data = requests.get(url).json()

    teams = {}

    stats = data.get("stats", [])[0].get("splits", [])

    for t in stats:
        name = t["team"]["name"]

        ops = float(t["stat"].get("ops", 0))
        runs = float(t["stat"].get("runs", 0))
        avg = float(t["stat"].get("avg", 0))

        # weighted composite offensive score
        score = (ops * 100) + (runs / 10) + (avg * 1000)

        teams[name] = score

    # normalize
    max_val = max(teams.values()) if teams else 1

    for k in teams:
        teams[k] = teams[k] / max_val

    return teams

TEAM_OFFENSE = get_team_offense_rankings()

# fallback safety
if not TEAM_OFFENSE:
    TEAM_OFFENSE = {}

# -----------------------------
# PITCHER IMPACT (REALISTIC SCALE)
# -----------------------------
def pitcher_strength(name):
    if name == "TBD":
        return 0

    elite = ["Cole", "Strider", "Burnes", "Skubal", "Wheeler", "Valdez"]
    good = ["Gausman", "Gray", "Rodon", "Lugo", "Taillon", "Pivetta"]

    for p in elite:
        if p in name:
            return 0.35
    for p in good:
        if p in name:
            return 0.15

    return 0.05

# -----------------------------
# LIVE TEAM STRENGTH
# -----------------------------
def team_strength(team):
    return TEAM_OFFENSE.get(team, 0.5)

# -----------------------------
# MONEYLINE MODEL
# -----------------------------
def win_prob(home, away, hp, ap):

    h = team_strength(home)
    a = team_strength(away)

    h += pitcher_strength(hp)
    a += pitcher_strength(ap)

    h += 0.03  # home advantage

    diff = (h - a)

    prob = 1 / (1 + math.exp(-diff * 8))

    return max(0.2, min(0.8, prob))

# -----------------------------
# RUN MODEL (LIVE DATA BASED)
# -----------------------------
def expected_runs(team, opp_pitcher):

    base = team_strength(team)

    pitch_adj = pitcher_strength(opp_pitcher)

    runs = 4.5 * base * (1 - pitch_adj)

    return max(2.0, min(6.5, runs))

# -----------------------------
# TOTALS
# -----------------------------
def totals_model(home, away, hp, ap):

    hr = expected_runs(home, ap)
    ar = expected_runs(away, hp)

    total = hr + ar

    return round(total, 2), round(hr, 2), round(ar, 2)

# -----------------------------
# SPREAD MODEL
# -----------------------------
def spread_model(home, away, hp, ap):

    h = expected_runs(home, ap)
    a = expected_runs(away, hp)

    return round(h - a, 2)

# -----------------------------
# EDGE FUNCTIONS
# -----------------------------
def ml_edge(p):
    return round((p - 0.5) * 100, 2)

def total_edge(t):
    return round((t - 8.5) * 5, 2)

def spread_edge(s):
    return round(s * 10, 2)

def grade(e):
    if abs(e) >= 5:
        return "🟢 BET"
    elif abs(e) >= 2:
        return "🟡 LEAN"
    return "🔴 NO BET"

# -----------------------------
# UI
# -----------------------------
st.header("📊 Live MLB Slate (Data Driven)")

for home, away, hp, ap in games:

    st.markdown("---")
    st.subheader(f"{away} @ {home}")

    col1, col2, col3 = st.columns(3)

    p = win_prob(home, away, hp, ap)

    total, hr, ar = totals_model(home, away, hp, ap)

    spread = spread_model(home, away, hp, ap)

    with col1:
        st.write("🏟️ Pitchers")
        st.write(f"Away: {ap}")
        st.write(f"Home: {hp}")

        e = ml_edge(p)
        st.write("📈 Moneyline")
        st.write(f"Win Prob: {round(p*100,2)}%")
        st.write(f"Edge: {e}% {grade(abs(e))}")

    with col2:
        e2 = total_edge(total)

        st.write("⚾ Totals")
        st.write(f"Projected: {total}")
        st.write(f"{home}: {hr}")
        st.write(f"{away}: {ar}")
        st.write(f"Edge: {e2}% {grade(abs(e2))}")

    with col3:
        e3 = spread_edge(spread)

        st.write("📊 Spread")
        st.write(f"Run Diff: {spread}")
        st.write(f"Edge: {e3}% {grade(abs(e3))}")

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
    st.info("No bets yet.")
