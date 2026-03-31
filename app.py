import streamlit as st
import requests
import math
import pandas as pd
from datetime import datetime

st.set_page_config(layout="wide")

st.title("⚾ MLB EV Engine V9")
st.subheader(f"📅 {datetime.now().strftime('%A %d %B %Y')}")

# =========================
# ODDS CONVERSION
# =========================
def american_to_prob(odds):

    if odds < 0:
        return (-odds) / (-odds + 100)
    else:
        return 100 / (odds + 100)

# =========================
# KELLY CRITERION
# =========================
def kelly(prob, odds):

    if odds > 0:
        b = odds / 100
    else:
        b = 100 / abs(odds)

    return max(0, (prob * (b + 1) - 1) / b)

# =========================
# TEAM STRENGTH
# =========================
def team_strength(team):

    base = {
        "Dodgers": 0.16, "Yankees": 0.13, "Braves": 0.15,
        "Astros": 0.11, "Phillies": 0.09, "Orioles": 0.10,
        "Mets": 0.04, "Mariners": 0.05, "Guardians": 0.03
    }

    return base.get(team, 0.0)

# =========================
# SIMPLE MODEL (VARIANCE FIXED VERSION)
# =========================
def model_prob(home_strength, away_strength):

    diff = home_strength - away_strength
    return 1 / (1 + math.exp(-diff * 6))

# =========================
# MLB GAMES (SAFE FALLBACK SAMPLE)
# Replace with your existing schedule function
# =========================
games = [
    {"home": "Dodgers", "away": "Giants"},
    {"home": "Yankees", "away": "Red Sox"},
    {"home": "Braves", "away": "Mets"},
]

# =========================
# UI STATE
# =========================
if "bets" not in st.session_state:
    st.session_state.bets = []

# =========================
# EV LOGIC
# =========================
def ev_calc(model_p, odds):

    book_p = american_to_prob(odds)
    return (model_p - book_p) * 100

def grade(ev):

    if ev >= 5:
        return "🟢 STRONG BET"
    if ev >= 2:
        return "🟡 LEAN"
    return "🔴 NO BET"

# =========================
# MAIN LOOP
# =========================
st.header("📊 Slate")

for g in games:

    st.markdown("---")

    home = g["home"]
    away = g["away"]

    home_strength = team_strength(home)
    away_strength = team_strength(away)

    p_home = model_prob(home_strength, away_strength)

    # FAKE odds placeholder (replace with sportsbook API later)
    odds_home = -110

    ev = ev_calc(p_home, odds_home)

    pick = home if p_home > 0.5 else away

    k = kelly(p_home, odds_home)

    st.subheader(f"{away} @ {home}")

    col1, col2 = st.columns(2)

    with col1:
        st.write("📈 Moneyline Model")
        st.write(f"Model Prob: {round(p_home*100,2)}%")
        st.write(f"Pick: {pick}")
        st.write(f"EV: {round(ev,2)}% {grade(ev)}")

    with col2:
        st.write("💰 Betting Info")
        st.write(f"Book Odds: -110")
        st.write(f"Implied Prob: {round(american_to_prob(odds_home)*100,2)}%")
        st.write(f"Kelly Stake: {round(k*100,2)}% bankroll")

    # =========================
    # TRACKER
    # =========================
    if st.button(f"➕ Add Bet {home}", key=home):

        st.session_state.bets.append({
            "game": f"{away} @ {home}",
            "pick": pick,
            "ev": round(ev,2),
            "kelly": round(k,4),
            "status": "OPEN"
        })

# =========================
# TRACKER TABLE
# =========================
st.header("📒 Bet Tracker")

if st.session_state.bets:
    st.dataframe(pd.DataFrame(st.session_state.bets))
else:
    st.info("No bets yet")
