import streamlit as st
import requests
import pandas as pd
import math
from datetime import datetime

st.set_page_config(layout="wide")

# =========================
# HEADER
# =========================
today = datetime.now().strftime("%A %d %B %Y")
st.title("⚾ MLB Betting Engine v7 (Pitcher + Weather Model)")
st.subheader(f"📅 Slate: {today}")

# =========================
# STATE
# =========================
if "bets" not in st.session_state:
    st.session_state.bets = []

# =========================
# MLB SCHEDULE
# =========================
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

# =========================
# PITCHER STATS (MLB API)
# =========================
PITCHER_CACHE = {}

def get_pitcher_stats(name):

    if name in PITCHER_CACHE:
        return PITCHER_CACHE[name]

    try:
        search = requests.get(
            f"https://statsapi.mlb.com/api/v1/people/search?names={name}"
        ).json()

        person = search["people"][0]
        pid = person["id"]

        stats = requests.get(
            f"https://statsapi.mlb.com/api/v1/people/{pid}/stats?stats=season&group=pitching"
        ).json()

        s = stats["stats"][0]["splits"][0]["stat"]

        data = {
            "era": float(s.get("era", 4.5)),
            "whip": float(s.get("whip", 1.3)),
            "k9": float(s.get("strikeoutsPer9Inn", 8.0)),
            "bb9": float(s.get("baseOnBallsPer9Inn", 3.0)),
            "ip": float(s.get("inningsPitched", 100))
        }

    except:
        data = {
            "era": 4.5,
            "whip": 1.3,
            "k9": 8.0,
            "bb9": 3.0,
            "ip": 100
        }

    PITCHER_CACHE[name] = data
    return data

# =========================
# PITCHER RATING
# =========================
def pitcher_rating(p):

    return (
        (4.5 - p["era"]) * 0.40 +
        (1.3 - p["whip"]) * 0.35 +
        (p["k9"] - 8) * 0.05 -
        (p["bb9"] - 3) * 0.06 +
        (p["ip"] / 200) * 0.2
    )

# =========================
# WEATHER MODEL
# =========================
def weather_factor(temp=75, wind=5):
    return (temp - 70) * 0.01 + wind * 0.02

# =========================
# TEAM STRENGTH MODEL
# =========================
def team_strength(team):

    base = {
        "Dodgers": 0.15, "Yankees": 0.12, "Braves": 0.14, "Astros": 0.10,
        "Phillies": 0.08, "Orioles": 0.09, "Rangers": 0.07,
        "Mets": 0.03, "Mariners": 0.04, "Guardians": 0.02,
        "Red Sox": 0.02, "Cubs": 0.03, "Padres": 0.05
    }

    return base.get(team, 0.00)

# =========================
# WIN PROBABILITY
# =========================
def win_prob(home, away, hp, ap):

    h_pitch = pitcher_rating(get_pitcher_stats(hp))
    a_pitch = pitcher_rating(get_pitcher_stats(ap))

    h = team_strength(home) + h_pitch + 0.05
    a = team_strength(away) + a_pitch

    diff = h - a

    return 1 / (1 + math.exp(-diff * 5))

# =========================
# RUN MODEL
# =========================
def expected_runs(team, pitcher, weather=0):

    p = pitcher_rating(get_pitcher_stats(pitcher))

    base = 4.3 + team_strength(team)

    return max(2.0, min(7.5, base - p + weather))

def totals_model(home, away, hp, ap, temp=75, wind=5):

    w = weather_factor(temp, wind)

    hr = expected_runs(home, ap, w)
    ar = expected_runs(away, hp, w)

    return round(hr + ar, 2), round(hr, 2), round(ar, 2)

# =========================
# SPREAD MODEL
# =========================
def spread_model(home, away, hp, ap):

    return round(expected_runs(home, ap) - expected_runs(away, hp), 2)

# =========================
# EDGE + GRADING
# =========================
def ml_edge(p):
    return round((p - 0.5) * 100, 2)

def total_edge(t):
    return round((t - 8.5) * 5, 2)

def spread_edge(s):
    return round(s * 10, 2)

def grade(e):
    if e <= 0:
        return "NO BET"
    if e >= 5:
        return "STRONG BET"
    if e >= 2:
        return "LEAN"
    return "NO BET"

# =========================
# PICK LOGIC
# =========================
def ml_pick(home, away, p):
    return home if p > 0.5 else away

# =========================
# UI
# =========================
st.header("📊 Full MLB Slate")

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

    pick = ml_pick(home, away, p)

    with col1:
        st.write("🏟️ Pitchers")
        st.write(f"Away: {ap}")
        st.write(f"Home: {hp}")

        st.write("📈 Moneyline")
        st.write(f"Win Prob: {round(p*100,2)}%")
        st.write(f"👉 PICK: {pick} ML")
        st.write(f"Edge: {ml_e}% {grade(ml_e)}")

    with col2:
        st.write("⚾ Totals")
        st.write(f"Projected: {total}")
        st.write(f"{home}: {hr}")
        st.write(f"{away}: {ar}")
        st.write(f"Edge: {t_e}% {grade(t_e)}")

    with col3:
        st.write("📊 Spread")
        st.write(f"Run Diff: {spread}")
        st.write(f"Edge: {s_e}% {grade(s_e)}")

    # =========================
    # BET TRACKER
    # =========================
    if st.button(f"➕ Add Bet {away} @ {home}", key=f"{away}_vs_{home}"):

        st.session_state.bets.append({
            "game": f"{away} @ {home}",
            "pick": pick,
            "ml_prob": round(p, 3),
            "ml_edge": ml_e,
            "total_edge": t_e,
            "spread_edge": s_e,
            "status": "open"
        })

        st.success(f"Added: {pick} ML")

# =========================
# TRACKER
# =========================
st.header("📒 Bet Tracker")

if st.session_state.bets:
    st.dataframe(pd.DataFrame(st.session_state.bets))
else:
    st.info("No bets added yet.")
