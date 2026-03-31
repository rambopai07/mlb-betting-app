import streamlit as st
import requests
import pandas as pd
import math
from datetime import datetime

st.set_page_config(layout="wide")

# -----------------------------
# HEADER
# -----------------------------
today = datetime.now().strftime("%A %d %B %Y")
st.title("⚾ MLB Betting Engine v6 (Fixed UX + Bets)")
st.subheader(f"📅 Slate: {today}")

# -----------------------------
# SESSION STATE
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
# LIVE TEAM STRENGTH (simplified stable version)
# -----------------------------
def team_strength(team):
    # lightweight proxy (stable, no API dependency failure risk)
    base = {
        "Dodgers": 1.25, "Yankees": 1.18, "Braves": 1.22, "Astros": 1.15,
        "Phillies": 1.10, "Orioles": 1.08, "Rangers": 1.07,
        "Mets": 1.02, "Mariners": 1.03, "Guardians": 1.00,
        "Red Sox": 0.99, "Cubs": 1.01, "Padres": 1.04
    }
    return base.get(team, 0.98)

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
            return 0.25
    for p in good:
        if p in name:
            return 0.10

    return 0.03

# -----------------------------
# MODELS
# -----------------------------
def win_prob(home, away, hp, ap):
    h = team_strength(home) + pitcher_strength(hp) + 0.02
    a = team_strength(away) + pitcher_strength(ap)

    diff = (h - a)

    return 1 / (1 + math.exp(-diff * 7))

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
# EDGE + GRADING
# -----------------------------
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

# -----------------------------
# PICK LOGIC (IMPORTANT FIX)
# -----------------------------
def ml_pick(home, away, prob_home):
    return home if prob_home > 0.5 else away

# -----------------------------
# UI
# -----------------------------
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

    # -----------------------------
    # BET TRACKER (FIXED KEY)
    # -----------------------------
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

        st.success(f"Added bet: {pick} ML")

# -----------------------------
# TRACKER
# -----------------------------
st.header("📒 Bet Tracker")

if st.session_state.bets:
    st.dataframe(pd.DataFrame(st.session_state.bets))
else:
    st.info("No bets added yet.")
