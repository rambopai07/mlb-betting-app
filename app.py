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
st.title("⚾ MLB Betting Engine v5 (Clean Logic Fix)")
st.subheader(f"📅 Slate: {today}")

# -----------------------------
# TRACKER
# -----------------------------
if "bets" not in st.session_state:
    st.session_state.bets = []

# -----------------------------
# MLB SCHEDULE
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
# LIVE TEAM STRENGTH (MLB API BASED)
# -----------------------------
def get_team_strengths():
    url = "https://statsapi.mlb.com/api/v1/stats?stats=season&group=hitting&sportId=1"
    data = requests.get(url).json()

    teams = {}
    stats = data.get("stats", [])[0].get("splits", [])

    for t in stats:
        name = t["team"]["name"]

        ops = float(t["stat"].get("ops", 0))
        runs = float(t["stat"].get("runs", 0))
        avg = float(t["stat"].get("avg", 0))

        score = (ops * 100) + (runs / 10) + (avg * 1000)
        teams[name] = score

    if not teams:
        return {}

    mx = max(teams.values())
    for k in teams:
        teams[k] /= mx

    return teams

TEAM = get_team_strengths()

# -----------------------------
# PITCHER IMPACT
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
# CORE MODELS
# -----------------------------
def team_strength(name):
    return TEAM.get(name, 0.5)

def win_prob(home, away, hp, ap):
    h = team_strength(home) + pitcher_strength(hp) + 0.03
    a = team_strength(away) + pitcher_strength(ap)

    diff = (h - a)

    return 1 / (1 + math.exp(-diff * 8))

def expected_runs(team, opp_pitch):
    base = team_strength(team)
    pitch = pitcher_strength(opp_pitch)

    return max(2.0, min(6.5, 4.5 * base * (1 - pitch)))

def totals_model(home, away, hp, ap):
    hr = expected_runs(home, ap)
    ar = expected_runs(away, hp)

    return round(hr + ar, 2), round(hr, 2), round(ar, 2)

def spread_model(home, away, hp, ap):
    return round(expected_runs(home, ap) - expected_runs(away, hp), 2)

# -----------------------------
# EDGE CALCULATION
# -----------------------------
def ml_edge(p):
    return round((p - 0.5) * 100, 2)

def total_edge(t):
    return round((t - 8.5) * 5, 2)

def spread_edge(s):
    return round(s * 10, 2)

# -----------------------------
# CLEAN GRADING (FIXED)
# -----------------------------
def grade(edge):
    if edge <= 0:
        return "NO BET"
    elif edge >= 5:
        return "STRONG BET"
    elif edge >= 2:
        return "LEAN"
    return "NO BET"

# -----------------------------
# DISPLAY
# -----------------------------
st.header("📊 Full Slate")

for home, away, hp, ap in games:

    st.markdown("---")
    st.subheader(f"{away} @ {home}")

    col1, col2, col3 = st.columns(3)

    p = win_prob(home, away, hp, ap)
    total, hr, ar = totals_model(home, away, hp, ap)
    spread = spread_model(home, away, hp, ap)

    ml_e = ml_edge(p)
    t_e = total_edge(total)
    s_e = spread_edge(spread)

    with col1:
        st.write("🏟️ Pitchers")
        st.write(f"Away: {ap}")
        st.write(f"Home: {hp}")

        st.write("📈 Moneyline")
        st.write(f"{round(p*100,2)}%")
        st.write(f"Edge: {ml_e}% {grade(ml_e)}")

    with col2:
        st.write("⚾ Totals")
        st.write(f"{total}")
        st.write(f"{home}: {hr}")
        st.write(f"{away}: {ar}")
        st.write(f"Edge: {t_e}% {grade(t_e)}")

    with col3:
        st.write("📊 Spread")
        st.write(f"{spread}")
        st.write(f"Edge: {s_e}% {grade(s_e)}")

    # BET TRACKER
    if st.button(f"➕ Add Bet {away} @ {home}", key=str(uuid.uuid4())):
        st.session_state.bets.append({
            "game": f"{away} @ {home}",
            "ml_edge": ml_e,
            "total_edge": t_e,
            "spread_edge": s_e,
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
