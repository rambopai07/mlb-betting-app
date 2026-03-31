import streamlit as st
import requests
import pandas as pd
import math
import os
from datetime import datetime

st.set_page_config(page_title="MLB Engine V22 Multi-Market", layout="wide")

API_KEY = "0d678e13097a84442df1e953f8fcaf95"
LOG_FILE = "bet_log.csv"

# ------------------ HELPERS ------------------ #

def sigmoid(x):
    return 1 / (1 + math.exp(-x))

def clamp(x, a, b):
    return max(a, min(b, x))

def american_to_decimal(o):
    return 1 + (100 / abs(o)) if o < 0 else 1 + (o / 100)

def ev(prob, odds):
    return (prob * odds) - 1

def clean(name):
    return (name or "").lower().strip()

# ------------------ CALIBRATION ------------------ #

def calibrate(prob):
    return clamp((prob * 0.92) + 0.04, 0.02, 0.98)

# ------------------ ODDS ------------------ #

def get_odds():
    url = "https://api.the-odds-api.com/v4/sports/baseball_mlb/odds"
    params = {
        "apiKey": API_KEY,
        "regions": "us,au",
        "markets": "h2h,spreads,totals",
        "oddsFormat": "american"
    }
    return requests.get(url, params=params).json()

# ------------------ TEAM MODEL ------------------ #

def get_team_strength():
    url = "https://statsapi.mlb.com/api/v1/teams?sportId=1"
    data = requests.get(url).json()

    teams = {}

    for t in data.get("teams", []):
        name = t["name"]
        base = (hash(name) % 40) / 100

        teams[name] = {
            "offense": 4.2 + base,
            "pitching": 4.2 + ((hash(name[::-1]) % 40) / 100),
            "bullpen": 4.1 + ((hash(name + "bp") % 30) / 100)
        }

    return teams

# ------------------ PITCHER MODEL ------------------ #

def pitcher_era(name):
    if not name:
        return 4.5

    try:
        r = requests.get(
            f"https://statsapi.mlb.com/api/v1/people/search?names={name}"
        ).json()

        people = r.get("people", [])
        if not people:
            return 4.5

        pid = people[0]["id"]

        s = requests.get(
            f"https://statsapi.mlb.com/api/v1/people/{pid}/stats?stats=season"
        ).json()

        splits = s.get("stats", [{}])[0].get("splits", [])
        if not splits:
            return 4.5

        return float(splits[0]["stat"].get("era", 4.5))

    except:
        return 4.5

# ------------------ 3 MARKET MODEL ------------------ #

def model(game, teams):

    home = game["home_team"]
    away = game["away_team"]

    h = teams.get(home, {})
    a = teams.get(away, {})

    offense = h.get("offense", 4.3) - a.get("offense", 4.3)
    pitching = h.get("pitching", 4.3) - a.get("pitching", 4.3)
    bullpen = h.get("bullpen", 4.3) - a.get("bullpen", 4.3)

    home_sp = pitcher_era(game.get("home_pitcher"))
    away_sp = pitcher_era(game.get("away_pitcher"))

    pitcher_edge = ((10 - home_sp) - (10 - away_sp)) / 2

    home_adv = 0.15

    # ------------------ MONEYLINE ------------------ #
    ml_edge = (
        0.35 * offense +
        0.25 * pitching +
        0.15 * bullpen +
        0.20 * pitcher_edge +
        0.05 * home_adv
    )

    win_prob = calibrate(sigmoid(ml_edge))

    # ------------------ TOTALS ------------------ #
    run_env = 8.6 + (offense * 1.8) - (pitching * 1.2)

    # pitcher adjustment affects scoring
    run_env += (home_sp + away_sp - 9.0) * 0.15

    # ------------------ SPREAD ------------------ #
    margin = ml_edge * 2.2

    return win_prob, run_env, margin, home_sp, away_sp

# ------------------ RAG ------------------ #

def classify(ev_score):
    if ev_score >= 0.05:
        return "🟢 GREEN"
    elif ev_score >= 0.01:
        return "🟡 AMBER"
    else:
        return "🔴 RED"

# ------------------ MAIN ------------------ #

st.title("⚾ MLB Engine V22 — FULL MARKET SYSTEM")

odds_data = get_odds()
teams = get_team_strength()

results = []
log_rows = []

for game in odds_data:

    home = game.get("home_team")
    away = game.get("away_team")

    if not home or not away:
        continue

    markets = game.get("bookmakers", [])
    if not markets:
        continue

    try:
        h2h = markets[0]["markets"]
        h2h = next(m for m in h2h if m["key"] == "h2h")
        spread = next(m for m in markets[0]["markets"] if m["key"] == "spreads")
        totals = next(m for m in markets[0]["markets"] if m["key"] == "totals")

        def price(market, team):
            return next((o["price"] for o in market["outcomes"] if clean(o["name"]) == clean(team)), None)

        home_ml = price(h2h, home)
        away_ml = price(h2h, away)

        if not home_ml or not away_ml:
            continue

    except:
        continue

    prob, run_env, margin, home_sp, away_sp = model(game, teams)

    # ------------------ MONEYLINE ------------------ #
    home_ev = ev(prob, american_to_decimal(home_ml))
    away_ev = ev(1 - prob, american_to_decimal(away_ml))

    ml_pick = home if home_ev > away_ev else away
    ml_ev = max(home_ev, away_ev)

    # ------------------ TOTALS ------------------ #
    total_line = 8.5
    total_ev = ev(
        1 if run_env > total_line else 0,
        1.91
    )

    total_pick = "OVER" if run_env > total_line else "UNDER"

    # ------------------ SPREAD ------------------ #
    spread_pick = home if margin > 1 else away
    spread_ev = abs(margin) * 0.03

    # ------------------ RAG ------------------ #
    ml_rating = classify(ml_ev)
    total_rating = classify(total_ev)
    spread_rating = classify(spread_ev)

    results.append({
        "Game": f"{away} @ {home}",

        # ML
        "ML Pick": ml_pick,
        "ML Rating": ml_rating,
        "ML EV%": round(ml_ev * 100, 2),

        # Totals
        "Total Pick": total_pick,
        "Total Rating": total_rating,
        "Total EV%": round(total_ev * 100, 2),

        # Spread
        "Spread Pick": spread_pick,
        "Spread Rating": spread_rating,
        "Spread EV%": round(spread_ev * 100, 2),

        # Pitchers
        "Home SP ERA": home_sp,
        "Away SP ERA": away_sp,
        "Projected Runs": round(run_env, 2)
    })

# ------------------ OUTPUT ------------------ #

df = pd.DataFrame(results)

st.subheader("📊 Full Market Recommendations")

st.dataframe(df.sort_values("ML EV%", ascending=False), use_container_width=True)
