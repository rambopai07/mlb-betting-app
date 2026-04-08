import streamlit as st
import pandas as pd
import numpy as np
import requests
from datetime import datetime

st.set_page_config(layout="wide")
st.title("⚾ MLB Betting Model V8 — Full Factors (Stable)")

# =========================
# CONFIG
# =========================

ODDS_API_KEY = "0d678e13097a84442df1e953f8fcaf95"

# =========================
# SAFE REQUEST
# =========================

def safe_get(url):
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.error(f"API Error: {e}")
        return {}

# =========================
# MLB GAMES
# =========================

def get_games():
    today = datetime.utcnow().strftime("%Y-%m-%d")

    url = f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={today}&hydrate=probablePitcher,team"
    data = safe_get(url)

    games = []

    for d in data.get("dates", []):
        for g in d.get("games", []):

            games.append({
                "home": g["teams"]["home"]["team"]["name"],
                "away": g["teams"]["away"]["team"]["name"],
                "home_id": g["teams"]["home"]["team"]["id"],
                "away_id": g["teams"]["away"]["team"]["id"],
                "home_pitcher": g["teams"]["home"].get("probablePitcher", {}).get("id"),
                "away_pitcher": g["teams"]["away"].get("probablePitcher", {}).get("id")
            })

    return games

# =========================
# PITCHER STATS (REAL MLB API)
# =========================

def pitcher_stats(pid):

    if pid is None:
        return {"era": 4.2, "whip": 1.3, "kbb": 2.0}

    url = f"https://statsapi.mlb.com/api/v1/people/{pid}/stats?stats=season&group=pitching"
    data = safe_get(url)

    try:
        s = data["stats"][0]["splits"][0]["stat"]

        era = float(s.get("era", 4.2))
        walks = float(s.get("baseOnBalls", 20))
        strikeouts = float(s.get("strikeOuts", 50))

        kbb = strikeouts / max(walks, 1)

        return {
            "era": era,
            "whip": era / 3.5,  # proxy (MLB API doesn't give WHIP cleanly)
            "kbb": kbb
        }

    except:
        return {"era": 4.2, "whip": 1.3, "kbb": 2.0}

# =========================
# TEAM OFFENSE + PITCHING
# =========================

def team_stats(team_id):

    url = f"https://statsapi.mlb.com/api/v1/teams/{team_id}/stats?stats=season"
    data = safe_get(url)

    try:
        s = data["stats"][0]["splits"][0]["stat"]

        return {
            "runs": float(s.get("runs", 700)),
            "obp": float(s.get("obp", 0.320)),
            "slg": float(s.get("slg", 0.400)),
            "era_team": float(s.get("era", 4.20)),
        }

    except:
        return {
            "runs": 700,
            "obp": 0.320,
            "slg": 0.400,
            "era_team": 4.20
        }

# =========================
# ODDS
# =========================

def get_odds():

    if ODDS_API_KEY == "YOUR_API_KEY":
        return {}

    url = f"https://api.the-odds-api.com/v4/sports/baseball_mlb/odds/?apiKey={ODDS_API_KEY}&regions=us&markets=h2h"
    data = safe_get(url)

    odds = {}

    for g in data:
        home = g.get("home_team")

        for b in g.get("bookmakers", []):
            for m in b.get("markets", []):
                if m.get("key") == "h2h":
                    for o in m.get("outcomes", []):
                        if o.get("name") == home:
                            odds[home] = o.get("price", 1.90)

    return odds

# =========================
# MODEL (FULL WEIGHTED ENGINE)
# =========================

def score_pitcher(p):
    return (
        -0.45 * p["era"] +
        0.35 * p["kbb"] -
        0.20 * p["whip"]
    )

def score_offense(t):
    return (
        0.40 * t["runs"] +
        0.30 * t["obp"] * 100 +
        0.30 * t["slg"] * 100
    )

def score_team(team, pitcher, is_home):

    pitch = score_pitcher(pitcher)
    offense = score_offense(team)

    home_adv = 0.15 if is_home else 0

    return pitch * 0.55 + offense * 0.35 + home_adv + (5 - team["era_team"])

# =========================
# PREDICTION ENGINE
# =========================

def predict(home, away, home_pitch, away_pitch, home_stats, away_stats, odds):

    home_score = score_team(home_stats, home_pitch, True)
    away_score = score_team(away_stats, away_pitch, False)

    diff = home_score - away_score

    prob_home = 1 / (1 + np.exp(-diff / 10))

    implied = 1 / odds if odds else 0.5

    edge = prob_home - implied

    return prob_home, edge

# =========================
# RUN
# =========================

st.write("Loading MLB games...")

games = get_games()

st.write(f"Games found: {len(games)}")

if len(games) == 0:
    st.warning("No games found or API issue.")
    st.stop()

odds_map = get_odds()

results = []

for g in games:

    home_stats = team_stats(g["home_id"])
    away_stats = team_stats(g["away_id"])

    home_pitch = pitcher_stats(g["home_pitcher"])
    away_pitch = pitcher_stats(g["away_pitcher"])

    odds = odds_map.get(g["home"], 1.90)

    prob, edge = predict(
        g["home"], g["away"],
        home_pitch, away_pitch,
        home_stats, away_stats,
        odds
    )

    bet = None
    if edge > 0.05:
        bet = "HOME ML"
    elif edge < -0.05:
        bet = "AWAY ML"

    results.append({
        "Game": f'{g["away"]} @ {g["home"]}',
        "Win Prob %": round(prob * 100, 1),
        "Edge %": round(edge * 100, 1),
        "Odds": odds,
        "Bet": bet
    })

df = pd.DataFrame(results)

st.subheader("📊 Full Model Predictions")
st.dataframe(df, use_container_width=True)

st.subheader("🔥 Value Bets")
st.dataframe(df[df["Edge %"].abs() > 5])
