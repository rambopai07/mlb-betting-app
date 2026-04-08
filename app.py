import streamlit as st
import pandas as pd
import numpy as np
import requests
from datetime import datetime

st.set_page_config(layout="wide")
st.title("⚾ MLB Betting Model V10 — Production Grade (Real Stats)")

# =========================
# CONFIG
# =========================

ODDS_API_KEY = "0d678e13097a84442df1e953f8fcaf95"

# =========================
# SAFE API CALL
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
                "home_team": g["teams"]["home"]["team"]["name"],
                "away_team": g["teams"]["away"]["team"]["name"],
                "home_id": g["teams"]["home"]["team"]["id"],
                "away_id": g["teams"]["away"]["team"]["id"],
                "home_pitcher_id": g["teams"]["home"].get("probablePitcher", {}).get("id"),
                "away_pitcher_id": g["teams"]["away"].get("probablePitcher", {}).get("id"),
                "home_pitcher_name": g["teams"]["home"].get("probablePitcher", {}).get("fullName", "TBD"),
                "away_pitcher_name": g["teams"]["away"].get("probablePitcher", {}).get("fullName", "TBD"),
            })

    return games

# =========================
# PITCHER STATS (REAL MLB API)
# =========================

def pitcher_stats(pid):

    if pid is None:
        return {"era": 4.2, "bb": 3.0, "so": 6.0}

    url = f"https://statsapi.mlb.com/api/v1/people/{pid}/stats?stats=season&group=pitching"
    data = safe_get(url)

    try:
        s = data["stats"][0]["splits"][0]["stat"]

        era = float(s.get("era", 4.2))
        bb = float(s.get("baseOnBalls", 30))
        so = float(s.get("strikeOuts", 80))

        return {
            "era": era,
            "bb": bb,
            "so": so
        }

    except:
        return {"era": 4.2, "bb": 3.0, "so": 6.0}

# =========================
# TEAM OFFENSE STATS (REAL)
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
        }

    except:
        return {
            "runs": 700,
            "obp": 0.320,
            "slg": 0.400
        }

# =========================
# ODDS
# =========================

def get_odds():

    if ODDS_API_KEY == "0d678e13097a84442df1e953f8fcaf95":
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
# FEATURE ENGINE
# =========================

def pitcher_strength(p):
    return (p["so"] / max(p["bb"], 1)) - (p["era"] / 5)

def offense_strength(t):
    return (t["runs"] / 1000) + t["obp"] + t["slg"]

# =========================
# MODEL
# =========================

def predict(home_team, away_team, home_p, away_p, home_t, away_t):

    home_pitch = pitcher_strength(home_p)
    away_pitch = pitcher_strength(away_p)

    home_off = offense_strength(home_t)
    away_off = offense_strength(away_t)

    home_adv = 0.15

    home_score = (home_pitch * 0.6) + (home_off * 0.4) + home_adv
    away_score = (away_pitch * 0.6) + (away_off * 0.4)

    diff = home_score - away_score

    prob_home = 1 / (1 + np.exp(-4.5 * diff))

    return prob_home

# =========================
# RUN
# =========================

st.write("Loading MLB games...")

games = get_games()

st.write(f"Games found: {len(games)}")

if len(games) == 0:
    st.stop()

odds_map = get_odds()

results = []

for g in games:

    home_p = pitcher_stats(g["home_pitcher_id"])
    away_p = pitcher_stats(g["away_pitcher_id"])

    home_t = team_stats(g["home_id"])
    away_t = team_stats(g["away_id"])

    prob = predict(
        g["home_team"],
        g["away_team"],
        home_p,
        away_p,
        home_t,
        away_t
    )

    odds = odds_map.get(g["home_team"], 1.90)

    implied = 1 / odds
    edge = prob - implied

    bet = None
    if edge > 0.05:
        bet = "HOME ML"
    elif edge < -0.05:
        bet = "AWAY ML"

    results.append({
        "Game": f'{g["away_team"]} @ {g["home_team"]}',
        "Home Pitcher": g["home_pitcher_name"],
        "Away Pitcher": g["away_pitcher_name"],
        "Win Prob %": round(prob * 100, 1),
        "Odds": odds,
        "Edge %": round(edge * 100, 1),
        "Bet": bet
    })

df = pd.DataFrame(results)

st.subheader("📊 Full Model Results")
st.dataframe(df, use_container_width=True)

st.subheader("🔥 Value Bets")
st.dataframe(df[df["Edge %"].abs() > 5])
