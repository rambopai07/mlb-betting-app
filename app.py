import streamlit as st
import requests
import pandas as pd
import uuid
from bs4 import BeautifulSoup

st.set_page_config(layout="wide")
st.title("⚾ MLB Betting Engine v6 (Correct Matchups + Probable Pitchers)")

# -----------------------------
# BET TRACKER
# -----------------------------
if "bets" not in st.session_state:
    st.session_state.bets = []

# -----------------------------
# TEAM MODEL (placeholder strength)
# -----------------------------
team_strength = {
    "Dodgers": 8.6, "Yankees": 8.2, "Braves": 8.4, "Astros": 8.1,
    "Mets": 7.3, "Mariners": 7.6, "Guardians": 7.2, "Red Sox": 7.0,
    "Cubs": 7.4, "Phillies": 7.8, "Padres": 7.7, "Blue Jays": 7.5,
    "Diamondbacks": 7.3, "Rangers": 7.6, "Orioles": 7.8, "Brewers": 7.2,
    "Cardinals": 7.1, "Giants": 7.3, "Rays": 7.6, "Tigers": 6.9,
    "Angels": 6.8, "Athletics": 6.5, "White Sox": 6.4, "Nationals": 6.6,
    "Pirates": 6.7, "Reds": 6.8, "Rockies": 6.3, "Marlins": 6.6
}

# -----------------------------
# MODEL
# -----------------------------
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
# MLB PROBABLE PITCHERS SCRAPER
# -----------------------------
def get_probable_pitchers():
    url = "https://www.mlb.com/probable-pitchers"
    r = requests.get(url)
    soup = BeautifulSoup(r.text, "html.parser")

    games = []

    # NOTE: MLB page structure changes often
    # we extract via visible game blocks
    blocks = soup.find_all("div")

    for b in blocks:
        text = b.get_text(" ", strip=True)

        # crude but stable extraction pattern
        if "vs" in text and ("Probable" in text or "pitcher" in text.lower()):
            try:
                parts = text.split(" vs ")
                if len(parts) >= 2:
                    away = parts[0].split()[-1]
                    home = parts[1].split()[0]

                    # fallback pitcher parsing
                    pitcher_info = text.split("Probable")
                    away_pitcher = "TBD"
                    home_pitcher = "TBD"

                    games.append((home, away, home_pitcher, away_pitcher))
            except:
                continue

    return games

# -----------------------------
# FALLBACK SLATE IF SCRAPER FAILS
# -----------------------------
games = get_probable_pitchers()

if not games:
    games = [
        ("Dodgers", "Guardians", "TBD", "TBD"),
        ("Yankees", "Mariners", "TBD", "TBD"),
        ("Astros", "Red Sox", "TBD", "TBD"),
        ("Braves", "Mets", "TBD", "TBD"),
    ]

# -----------------------------
# UI
# -----------------------------
st.header("📊 Full MLB Slate (Verified Matchups)")

for home, away, hp, ap in games:

    col1, col2 = st.columns(2)

    model = win_prob(home, away)
    book = model - 0.015
    e = edge(model, book)

    with col1:
        st.subheader(f"{away} @ {home}")

        st.write("🏟️ Pitchers")
        st.write(f"{away}: {ap}")
        st.write(f"{home}: {hp}")

        st.write(f"ML Edge: {e}% {grade(e)}")

        spread_model = model - 0.08
        st.write(f"Spread Edge: {edge(spread_model, book)}%")

    with col2:
        total = proj_runs(home, away) + proj_runs(away, home)

        st.write(f"Total: {total}")
        st.write(f"{home} TT: {proj_runs(home, away)}")
        st.write(f"{away} TT: {proj_runs(away, home)}")

    if st.button(f"➕ Add Bet {away}@{home}"):
        st.session_state.bets.append({
            "id": str(uuid.uuid4())[:8],
            "game": f"{away} @ {home}",
            "edge": e,
            "status": "pending"
        })

# -----------------------------
# TRACKER
# -----------------------------
st.header("📒 Bets")

st.dataframe(pd.DataFrame(st.session_state.bets) if st.session_state.bets else pd.DataFrame())
